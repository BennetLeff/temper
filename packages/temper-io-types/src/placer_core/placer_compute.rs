//! Wave-4 Phase 4: the placer's non-`cp_sat` placement compute in Rust.
//!
//! This is the pure Rust home of the kernels behind
//! `temper_placer/placer/adjustment.py`, `deterministic.py` and
//! `template.py` (the `placer/*.py` MIGRATE slice of
//! `docs/wave4-verdicts.yaml`). It compiles for `wasm32-unknown-unknown`
//! with no pyo3 dependency; the `#[cfg(feature = "python")]` boundary in
//! [`super::pybridge`] is the only place that touches Python objects.
//!
//! ## What moves here, and what deliberately stays in the shims
//!
//! Migrated (transcribed op-for-op from the pinned pre-migration oracles in
//! `packages/temper-placer/tests/placer/_placer_*_py_oracle.py`):
//!
//! * `apply_component_template` / `apply_parametric_template` — the anchor
//!   offset, per-component relative scaling, KiCad R(-θ) rotation around
//!   the anchor, absolute placement and floored-modulo composite rotation.
//! * `place_by_proximity` — the spiral loop (the #763-fixed function-level
//!   loop, including the `zone_name=None` path), angle step, clamp.
//! * `place_in_zone_center` — the grid distribution loop and clamp.
//! * `place_power_stage_template` — template application at the zone center
//!   plus the per-component mapping loop into the float32 position /
//!   rotation arrays.
//! * `adjust_for_congestion` — the per-(bottleneck, component) push loop,
//!   dtype-aware (float32 chains stay float32 under numpy 2.x NEP-50).
//!
//! Kept in the Python shims as library/object-navigation seams (the R1e
//! VERIFICATION.md records the scorecard):
//!
//! * The template dataclasses, their `create_*` data constructors and
//!   `load_template_from_yaml` (`yaml.safe_load` is a Python library).
//! * Zone / netlist / component attribute navigation (`.zones`, `.bounds`,
//!   `.components[].ref/.fixed`, `.n_components`, `bottleneck.overflow`,
//!   `bottleneck.to_coordinates(...)`).
//! * The transcendental functions and the RNG — passed in as callbacks.
//!   CPython's `math.cos`/`math.sin`, numpy's `**2` (libm `pow`, which is
//!   NOT `x*x` — measured diverging on both dtypes), numpy's correctly-
//!   rounded float32 `sqrt`, and `np.random.uniform` are all library
//!   semantics the oracle's bits depend on; Rust `f64::sin` is 1-ULP-
//!   divergent from CPython's `math.sin` on this platform (measured
//!   461/200k, 2026-08-05). The kernels call the Python-provided callbacks,
//!   so bit-identity holds by construction.
//!
//! ## Bit-exactness contract
//!
//! Everything the kernels compute themselves is IEEE-754 correctly-rounded
//! arithmetic (`+ - * /`, `sqrt`) in the oracle's exact evaluation order, so
//! it is bit-identical to numpy/Python scalar arithmetic on the same double
//! (numpy float64 scalar ops are IEEE). Two CPython semantics are reproduced
//! explicitly:
//!
//! * `py_mod` — Python's floored `%` (a negative operand must not produce a
//!   negative remainder the way Rust's `%` does).
//! * `py_min` / `py_max` — CPython's `min`/`max` first-arg-on-tie and NaN
//!   handling (comparison False yields the first argument).

/// One component's template entry: ref + relative geometry + rotation.
#[derive(Debug, Clone)]
pub struct TemplateComponent {
    pub ref_: String,
    pub x: f64,
    pub y: f64,
    pub rotation: i64,
}

/// One absolute placement produced by applying a template.
#[derive(Debug, Clone)]
pub struct TemplatePlacement {
    pub ref_: String,
    pub x: f64,
    pub y: f64,
    pub rotation: i64,
}

/// The result of `place_power_stage_template`-style placement.
#[derive(Debug)]
pub struct PlacerTemplateResult {
    /// Flat row-major float32 positions, `2 * n_components` wide.
    pub positions: Vec<f32>,
    /// Flat float32 rotations, `n_components` wide.
    pub rotations: Vec<f32>,
    pub placed: Vec<String>,
    pub unplaced: Vec<String>,
}

/// Python's floored `%` on integers for a positive modulus.
#[inline]
pub fn py_mod(a: i64, b: i64) -> i64 {
    debug_assert!(b > 0);
    let r = a % b;
    if r < 0 {
        r + b
    } else {
        r
    }
}

/// CPython's `max(a, b)` semantics on floats: the second argument wins only
/// when strictly greater, so a tie or a NaN keeps the first argument.
#[inline]
pub fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// CPython's `min(a, b)` semantics on floats: the second argument wins only
/// when strictly smaller, so a tie or a NaN keeps the first argument.
#[inline]
pub fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// `math.radians(rotation)`: CPython computes `x * (pi/180)` (the precomputed
/// ratio), NOT `(x*pi)/180`. The two disagree on 29.6% of inputs per the
/// Phase-2 units measurement; the ratio form is the oracle's.
#[inline]
fn rotation_radians(rotation: i64) -> f64 {
    (rotation as f64) * (std::f64::consts::PI / 180.0)
}

/// `ComponentTemplate.apply` compute (the oracle body transcribed).
///
/// `components[anchor_idx]` is the anchor; the shim guarantees it exists
/// (the oracle raises before the kernel is reached).
pub fn apply_component_template<E>(
    components: &[TemplateComponent],
    anchor_idx: usize,
    anchor_x: f64,
    anchor_y: f64,
    rotation: i64,
    cos_sin: &dyn Fn(f64) -> Result<(f64, f64), E>,
) -> Result<Vec<TemplatePlacement>, E> {
    let anchor = &components[anchor_idx];
    let anchor_offset_x = anchor.x;
    let anchor_offset_y = anchor.y;
    let rot_rad = rotation_radians(rotation);

    let mut placements = Vec::with_capacity(components.len());
    for comp in components {
        // Position relative to the anchor.
        let rel_x = comp.x - anchor_offset_x;
        let rel_y = comp.y - anchor_offset_y;

        // Rotate around the anchor, KiCad's real footprint/group rotation
        // convention (R(-theta)): (x*c + y*s, -x*s + y*c).
        let (rotated_x, rotated_y) = if rotation != 0 {
            let (c, s) = cos_sin(rot_rad)?;
            (rel_x * c + rel_y * s, -rel_x * s + rel_y * c)
        } else {
            (rel_x, rel_y)
        };

        let abs_x = anchor_x + rotated_x;
        let abs_y = anchor_y + rotated_y;
        let abs_rotation = py_mod(rotation + comp.rotation, 360);

        placements.push(TemplatePlacement {
            ref_: comp.ref_.clone(),
            x: abs_x,
            y: abs_y,
            rotation: abs_rotation,
        });
    }
    Ok(placements)
}

/// `ParametricTemplate.apply` compute (the oracle body transcribed).
///
/// `anchor_ratio` is the anchor component's `(x_ratio, y_ratio)`; `None`
/// selects the oracle's "default to center" fallback (`0.5 * target`).
#[allow(clippy::too_many_arguments)] // mirrors ParametricTemplate.apply's Python signature
pub fn apply_parametric_template<E>(
    components: &[TemplateComponent],
    anchor_ratio: Option<(f64, f64)>,
    anchor_x: f64,
    anchor_y: f64,
    target_width: f64,
    target_height: f64,
    rotation: i64,
    cos_sin: &dyn Fn(f64) -> Result<(f64, f64), E>,
) -> Result<Vec<TemplatePlacement>, E> {
    let (anchor_off_x, anchor_off_y) = match anchor_ratio {
        Some((rx, ry)) => (rx * target_width, ry * target_height),
        None => (0.5 * target_width, 0.5 * target_height),
    };
    let rot_rad = rotation_radians(rotation);

    let mut placements = Vec::with_capacity(components.len());
    for comp in components {
        // Scale to the target dimensions, relative to the anchor.
        let rel_x = comp.x * target_width - anchor_off_x;
        let rel_y = comp.y * target_height - anchor_off_y;

        let (rotated_x, rotated_y) = if rotation != 0 {
            let (c, s) = cos_sin(rot_rad)?;
            (rel_x * c + rel_y * s, -rel_x * s + rel_y * c)
        } else {
            (rel_x, rel_y)
        };

        let abs_x = anchor_x + rotated_x;
        let abs_y = anchor_y + rotated_y;
        let abs_rotation = py_mod(rotation + comp.rotation, 360);

        placements.push(TemplatePlacement {
            ref_: comp.ref_.clone(),
            x: abs_x,
            y: abs_y,
            rotation: abs_rotation,
        });
    }
    Ok(placements)
}

/// `place_power_stage_template` compute: apply the template at the zone
/// center, then map placements onto the float32 position/rotation arrays.
///
/// `component_refs` are the netlist components in order; `initial` is the
/// optional flat `2 * n_components` f64 view of the already-float32-cast
/// `initial_positions` (the shim performs the oracle's
/// `np.array(initial_positions, dtype=np.float32)` cast before passing it).
///
/// The mapping loop reproduces the oracle's `ref_to_idx` last-wins dict:
/// `idx = ref_to_idx[comp.ref]` resolves every occurrence of a duplicated
/// ref to its LAST index, and a ref present in the template is placed at
/// that last index (both occurrences push to `placed`, like the oracle's
/// loop body).
#[allow(clippy::too_many_arguments)] // mirrors place_power_stage_template's Python signature
pub fn place_power_stage_template<E>(
    component_refs: &[String],
    template_components: &[TemplateComponent],
    anchor_idx: usize,
    zone_center_x: f64,
    zone_center_y: f64,
    rotation: i64,
    initial: Option<&[f64]>,
    cos_sin: &dyn Fn(f64) -> Result<(f64, f64), E>,
) -> Result<PlacerTemplateResult, E> {
    let n = component_refs.len();
    let placements = apply_component_template(
        template_components,
        anchor_idx,
        zone_center_x,
        zone_center_y,
        rotation,
        cos_sin,
    )?;

    // ref -> last index (the oracle's `{comp.ref: i for i, comp in
    // enumerate(netlist.components)}` dict, last occurrence wins).
    let mut ref_to_idx = std::collections::HashMap::with_capacity(n);
    for (i, r) in component_refs.iter().enumerate() {
        ref_to_idx.insert(r.as_str(), i);
    }

    // ref -> placement (the oracle's `placements` dict: the template's own
    // apply() assigns `placements[comp.ref] = ...` in template order, so a
    // duplicated template ref resolves to its LAST geometry; the mapping
    // loop below then reads that single entry).
    let mut placements_by_ref: std::collections::HashMap<&str, &TemplatePlacement> =
        std::collections::HashMap::with_capacity(placements.len());
    for p in &placements {
        placements_by_ref.insert(p.ref_.as_str(), p);
    }

    // ref -> (x, y, rot). The oracle iterates the netlist components in
    // order, and `ref_to_idx` is last-wins on duplicates.
    let mut positions = match initial {
        Some(flat) => flat.iter().map(|v| *v as f32).collect::<Vec<f32>>(),
        None => vec![0.0f32; 2 * n],
    };
    let mut rotations = vec![0.0f32; n];
    let mut placed = Vec::new();
    let mut unplaced = Vec::new();

    for comp_ref in component_refs {
        if let Some(p) = placements_by_ref.get(comp_ref.as_str()) {
            let idx = ref_to_idx[comp_ref.as_str()];
            positions[2 * idx] = p.x as f32;
            positions[2 * idx + 1] = p.y as f32;
            rotations[idx] = p.rotation as f32;
            placed.push(comp_ref.clone());
        } else {
            unplaced.push(comp_ref.clone());
        }
    }

    Ok(PlacerTemplateResult {
        positions,
        rotations,
        placed,
        unplaced,
    })
}

/// `place_by_proximity` compute: the #763-fixed function-level spiral loop.
///
/// `indices[i]` is `ref_to_idx.get(refs[i])` — `None` for a ref absent from
/// the netlist (lands in `unplaced`, exactly like the oracle's `continue`).
/// `zone` bounds clamp the placed coordinates (CPython `min`/`max` first-
/// arg-on-tie semantics). The oracle's `max_distance` branch is a literal
/// no-op (`if distance > max_distance: pass`) and is not transcribed.
#[allow(clippy::type_complexity)] // the (positions, placed, unplaced) triple is the oracle's contract
pub fn place_by_proximity<E>(
    n_components: usize,
    refs: &[String],
    indices: &[Option<usize>],
    base_x: f64,
    base_y: f64,
    zone: Option<(f64, f64, f64, f64)>,
    cos_sin: &dyn Fn(f64) -> Result<(f64, f64), E>,
) -> Result<(Vec<f32>, Vec<String>, Vec<String>), E> {
    let angle_step = 2.0 * std::f64::consts::PI / (refs.len().max(4)) as f64;

    let mut positions = vec![0.0f32; 2 * n_components];
    let mut placed = Vec::new();
    let mut unplaced = Vec::new();

    for (i, (r, idx)) in refs.iter().zip(indices.iter()).enumerate() {
        let Some(idx) = idx else {
            unplaced.push(r.clone());
            continue;
        };
        let idx = *idx;

        let angle = (i as f64) * angle_step;
        let distance = 8.0 + ((i / 4) as f64) * 3.0; // Spiral outward

        let (c, s) = cos_sin(angle)?;
        let mut x = base_x + distance * c;
        let mut y = base_y + distance * s;

        // Clamp to the zone if specified.
        if let Some((x0, y0, x1, y1)) = zone {
            x = py_max(x0, py_min(x1, x));
            y = py_max(y0, py_min(y1, y));
        }

        positions[2 * idx] = x as f32;
        positions[2 * idx + 1] = y as f32;
        placed.push(r.clone());
    }

    Ok((positions, placed, unplaced))
}

/// `place_in_zone_center` compute: grid distribution around the zone center.
pub fn place_in_zone_center(
    n_components: usize,
    refs: &[String],
    indices: &[Option<usize>],
    center_x: f64,
    center_y: f64,
    zone: (f64, f64, f64, f64),
) -> (Vec<f32>, Vec<String>, Vec<String>) {
    let grid_size = ((refs.len() as f64).sqrt().ceil()) as usize;
    let spacing = 8.0;

    let mut positions = vec![0.0f32; 2 * n_components];
    let mut placed = Vec::new();
    let mut unplaced = Vec::new();

    for (i, (r, idx)) in refs.iter().zip(indices.iter()).enumerate() {
        let Some(idx) = idx else {
            unplaced.push(r.clone());
            continue;
        };
        let idx = *idx;

        let row = i / grid_size;
        let col = i % grid_size;

        let mut x = center_x + (col as f64 - grid_size as f64 / 2.0) * spacing;
        let mut y = center_y + (row as f64 - grid_size as f64 / 2.0) * spacing;

        // Clamp to the zone.
        x = py_max(zone.0, py_min(zone.2, x));
        y = py_max(zone.1, py_min(zone.3, y));

        positions[2 * idx] = x as f32;
        positions[2 * idx + 1] = y as f32;
        placed.push(r.clone());
    }

    (positions, placed, unplaced)
}

/// `adjust_for_congestion` compute: the per-(bottleneck, component) push loop.
///
/// Dtype-aware: with `is_f32`, the normalized-push chain is computed in f32
/// (numpy 2.x NEP-50 keeps a float32 array's arithmetic in float32, so
/// `dx = px - bx` rounds to f32), while the exact-spot random-push branch
/// adds the f64 random delta to the widened f32 element and rounds only on
/// store. The returned vector is the flat f64 view the shim writes back into
/// the caller's (copy of the) array, whose own dtype cast reproduces the
/// oracle's store.
///
/// `dist` is the numpy `sqrt(dx**2 + dy**2)` callback (numpy `**2` is libm
/// `pow`, not `x*x`; float32 `sqrt` is correctly rounded to f32); `uniform`
/// is `np.random.uniform(0, 2*pi)` drawn in the oracle's exact iteration
/// order; `cos_sin` applies to the random angle. Bottleneck coordinates are
/// precomputed by the shim (`bottleneck.to_coordinates` stays Python).
#[allow(clippy::too_many_arguments)] // mirrors adjust_for_congestion's Python seam surface
pub fn adjust_for_congestion<E>(
    positions: &[f64],
    is_f32: bool,
    fixed: &[bool],
    bottlenecks: &[(f64, f64)],
    push_strength: f64,
    influence_radius: f64,
    dist_cb: &dyn Fn(f64, f64) -> Result<f64, E>,
    uniform_cb: &dyn Fn() -> Result<f64, E>,
    cos_sin: &dyn Fn(f64) -> Result<(f64, f64), E>,
) -> Result<Vec<f64>, E> {
    let mut result = positions.to_vec();

    if is_f32 {
        let push32 = push_strength as f32;
        let infl32 = influence_radius as f32;
        let spot = 1e-3f32;
        for (bx, by) in bottlenecks {
            let bx32 = *bx as f32;
            let by32 = *by as f32;
            for (i, &fixed_i) in fixed.iter().enumerate() {
                if fixed_i {
                    continue;
                }
                let px32 = result[2 * i] as f32;
                let py32 = result[2 * i + 1] as f32;
                let dx32 = px32 - bx32;
                let dy32 = py32 - by32;
                let dist = dist_cb(dx32 as f64, dy32 as f64)?;
                let dist32 = dist as f32;
                if dist32 < infl32 {
                    if dist32 < spot {
                        // At the exact spot: random push. The f64 delta is
                        // added to the widened f32 element and rounded on
                        // store, exactly like numpy's in-place += on the
                        // float32 array.
                        let angle = uniform_cb()?;
                        let (c, s) = cos_sin(angle)?;
                        result[2 * i] = (px32 as f64) + push_strength * c;
                        result[2 * i + 1] = (py32 as f64) + push_strength * s;
                    } else {
                        // Normalized push: the whole chain stays f32.
                        let force = push32 * (1.0f32 - dist32 / infl32);
                        let dx_term = force * dx32 / dist32;
                        let dy_term = force * dy32 / dist32;
                        result[2 * i] = (px32 + dx_term) as f64;
                        result[2 * i + 1] = (py32 + dy_term) as f64;
                    }
                }
            }
        }
    } else {
        for (bx, by) in bottlenecks {
            for (i, &fixed_i) in fixed.iter().enumerate() {
                if fixed_i {
                    continue;
                }
                let px = result[2 * i];
                let py = result[2 * i + 1];
                let dx = px - bx;
                let dy = py - by;
                let dist = dist_cb(dx, dy)?;
                if dist < influence_radius {
                    if dist < 1e-3 {
                        // At the exact spot: random push.
                        let angle = uniform_cb()?;
                        let (c, s) = cos_sin(angle)?;
                        result[2 * i] = px + push_strength * c;
                        result[2 * i + 1] = py + push_strength * s;
                    } else {
                        // Normalized push.
                        let force = push_strength * (1.0 - dist / influence_radius);
                        result[2 * i] = px + force * dx / dist;
                        result[2 * i + 1] = py + force * dy / dist;
                    }
                }
            }
        }
    }

    Ok(result)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    // test-only kernel-driving helpers; the lib surface has none.  The
    // `unwrap_used` allow that licenses them is the generated OUTER attribute
    // above; an inner `#![allow(clippy::unwrap_used)]` as well is what clippy
    // calls `duplicated_attributes` + `mixed_attributes_style`, and CI runs
    // clippy with `--all-features`, which now includes `wasm-registry`.

    use super::*;

    fn cos_sin(theta: f64) -> Result<(f64, f64), ()> {
        Ok((theta.cos(), theta.sin()))
    }

    fn no_trig(theta: f64) -> Result<(f64, f64), ()> {
        let _ = theta;
        Ok((1.0, 0.0))
    }

    #[cfg_attr(test, test)]
    fn py_mod_floors_for_negative() {
        assert_eq!(py_mod(270 + 90, 360), 0);
        assert_eq!(py_mod(-90, 360), 270);
        assert_eq!(py_mod(90 + 270, 360), 0);
        assert_eq!(py_mod(45 + 359, 360), 44);
    }

    #[cfg_attr(test, test)]
    fn py_min_max_first_arg_on_tie_and_nan() {
        // CPython: min(2.0, 2.0) == 2.0, min(2.0, nan) == 2.0,
        // max(2.0, nan) == 2.0 (comparisons with NaN are False).
        assert_eq!(py_min(2.0, 2.0), 2.0);
        assert_eq!(py_max(2.0, 2.0), 2.0);
        assert_eq!(py_min(2.0, f64::NAN), 2.0);
        assert_eq!(py_max(2.0, f64::NAN), 2.0);
        assert!(py_min(f64::NAN, 2.0).is_nan());
        assert_eq!(py_min(1.0, 3.0), 1.0);
        assert_eq!(py_min(3.0, 1.0), 1.0);
        assert_eq!(py_max(1.0, 3.0), 3.0);
    }

    #[cfg_attr(test, test)]
    fn rotation_zero_is_identity() {
        // At rotation=0 the oracle never calls trig; the rel offsets pass
        // through and the composite rotation is py_mod(0 + comp_rot, 360).
        let comps = [
            TemplateComponent {
                ref_: "Q1".into(),
                x: 0.0,
                y: 0.0,
                rotation: 0,
            },
            TemplateComponent {
                ref_: "Q2".into(),
                x: 0.0,
                y: -20.0,
                rotation: 0,
            },
            TemplateComponent {
                ref_: "D1".into(),
                x: 10.0,
                y: 0.0,
                rotation: 90,
            },
        ];
        let out = apply_component_template(&comps, 0, 25.0, 25.0, 0, &no_trig).unwrap();
        assert_eq!(out[0].x, 25.0);
        assert_eq!(out[0].y, 25.0);
        assert_eq!(out[1].x, 25.0);
        assert_eq!(out[1].y, 5.0);
        assert_eq!(out[2].rotation, 90);
    }

    #[cfg_attr(test, test)]
    fn negative_rotation_composite_modulo() {
        // rotation=-90 + comp.rotation=90 -> 0 (Python floored modulo), NOT
        // Rust's truncated -0 % 360 == 0 anyway; use -45 + 90 -> 45.
        let comps = [TemplateComponent {
            ref_: "Q1".into(),
            x: 1.0,
            y: 2.0,
            rotation: 90,
        }];
        let out = apply_component_template(&comps, 0, 0.0, 0.0, -45, &no_trig).unwrap();
        assert_eq!(out[0].rotation, 45);
        // -90 + 270 -> 180, the case that would go negative under Rust `%`.
        let comps = [TemplateComponent {
            ref_: "Q1".into(),
            x: 1.0,
            y: 2.0,
            rotation: 270,
        }];
        let out = apply_component_template(&comps, 0, 0.0, 0.0, -90, &no_trig).unwrap();
        assert_eq!(out[0].rotation, 180);
    }

    #[cfg_attr(test, test)]
    fn proximity_spiral_runs_without_zone() {
        // The #763 contract: the zone_name=None path must place refs.
        let refs = vec!["C1".to_string()];
        let indices = vec![Some(0)];
        let (pos, placed, unplaced) =
            place_by_proximity(1, &refs, &indices, 50.0, 50.0, None, &cos_sin).unwrap();
        assert_eq!(placed, vec!["C1".to_string()]);
        assert!(unplaced.is_empty());
        // i=0: angle 0, distance 8.0 -> (58.0, 50.0).
        assert_eq!(pos[0], 58.0);
        assert_eq!(pos[1], 50.0);
    }

    #[cfg_attr(test, test)]
    fn proximity_unknown_ref_unplaced() {
        let refs = vec!["C1".to_string(), "MISSING".to_string()];
        let indices = vec![Some(0), None];
        let (_, placed, unplaced) =
            place_by_proximity(1, &refs, &indices, 0.0, 0.0, None, &cos_sin).unwrap();
        assert_eq!(placed, vec!["C1".to_string()]);
        assert_eq!(unplaced, vec!["MISSING".to_string()]);
    }

    #[cfg_attr(test, test)]
    fn zone_center_grid_lays_out_around_center() {
        let refs = vec!["U1".to_string(), "C1".to_string()];
        let indices = vec![Some(0), Some(1)];
        let (pos, _, _) =
            place_in_zone_center(2, &refs, &indices, 75.0, 75.0, (50.0, 50.0, 100.0, 100.0));
        // grid_size = ceil(sqrt(2)) = 2; x = center + (col - 2/2)*8.
        // U1 (i=0): row=0, col=0 -> (67, 67); C1 (i=1): row=0, col=1 -> (75, 67).
        assert_eq!(pos[0], 67.0);
        assert_eq!(pos[1], 67.0);
        assert_eq!(pos[2], 75.0);
        assert_eq!(pos[3], 67.0);
    }

    #[cfg_attr(test, test)]
    fn congestion_float64_normalized_push() {
        // dist = sqrt(pow(50.5-50.5,2) + pow(50.5-50.5,2)) = 0 < 1e-3 ->
        // random push. With a dist_cb that says dist is huge, no push.
        let big = |_: f64, _: f64| -> Result<f64, ()> { Ok(1e9) };
        let positions = vec![50.5, 50.5];
        let fixed = vec![false];
        let b = vec![(50.5, 50.5)];
        let out = adjust_for_congestion(
            &positions,
            false,
            &fixed,
            &b,
            2.0,
            10.0,
            &big,
            &|| Ok(1.0),
            &cos_sin,
        )
        .unwrap();
        assert_eq!(out, positions);
    }

    #[cfg_attr(test, test)]
    fn power_stage_duplicate_refs_resolve_to_last_index() {
        // The oracle's `ref_to_idx` is a last-wins dict: a duplicated ref
        // resolves to its LAST index, and both occurrences land there (and
        // both append to `placed`).
        let refs = vec!["Q1".to_string(), "Q2".to_string(), "Q1".to_string()];
        let template = [TemplateComponent {
            ref_: "Q1".into(),
            x: 0.0,
            y: 0.0,
            rotation: 0,
        }];
        let out =
            place_power_stage_template(&refs, &template, 0, 25.0, 25.0, 0, None, &no_trig).unwrap();
        assert_eq!(out.positions[0], 0.0); // first "Q1" keeps its zero
        assert_eq!(out.positions[1], 0.0);
        assert_eq!(out.positions[4], 25.0); // last "Q1" gets the placement
        assert_eq!(out.positions[5], 25.0);
        assert_eq!(out.placed, vec!["Q1".to_string(), "Q1".to_string()]);
        assert_eq!(out.unplaced, vec!["Q2".to_string()]);
    }

    #[cfg_attr(test, test)]
    fn power_stage_duplicate_template_ref_last_geometry_wins() {
        // The oracle's `placements` dict is last-wins on the TEMPLATE side
        // too: `placements[comp.ref] = ...` runs in template order, so a
        // duplicated template ref resolves to its LAST geometry (the netlist
        // mapping then reads that single entry).
        let refs = vec!["Q1".to_string(), "Q2".to_string()];
        let template = [
            TemplateComponent {
                ref_: "Q1".into(),
                x: 0.0,
                y: 0.0,
                rotation: 0,
            },
            TemplateComponent {
                ref_: "Q1".into(),
                x: 12.0,
                y: 8.0,
                rotation: 90,
            },
        ];
        // anchor_idx=1 -> the duplicate IS the anchor; last geometry wins.
        let out = place_power_stage_template(&refs, &template, 1, 25.0, 25.0, 0, None, &no_trig)
            .unwrap();
        assert_eq!(out.positions[0], 25.0);
        assert_eq!(out.positions[1], 25.0);
        assert_eq!(out.rotations[0], 90.0);
    }

    #[cfg_attr(test, test)]
    fn congestion_float32_chain_uses_f32_intermediates() {
        // A float32 input: dx = px - bx rounds to f32 (NEP-50), and the
        // normalized push chain is f32 arithmetic throughout.
        let dist = |dx: f64, dy: f64| -> Result<f64, ()> {
            let d32 = |v: f64| v as f32 as f64;
            let sq = (d32(dx) * d32(dx)) + (d32(dy) * d32(dy));
            Ok((sq as f32).sqrt() as f64)
        };
        let positions = vec![0.1, 0.2];
        let fixed = vec![false];
        let b = vec![(0.2, 0.3)];
        // dx = f32(0.1) - f32(0.2) = -0.10000000149011612, not the f64
        // -0.09999999850988388 the float64 path would compute.
        let out = adjust_for_congestion(
            &positions,
            true,
            &fixed,
            &b,
            2.0,
            10.0,
            &dist,
            &|| Ok(1.0),
            &cos_sin,
        )
        .unwrap();
        let x = out[0] as f32;
        let y = out[1] as f32;
        let dx32 = (0.1f32) - (0.2f32);
        let dy32 = (0.2f32) - (0.3f32);
        let dist32 = (dx32 * dx32 + dy32 * dy32).sqrt();
        let force32 = 2.0f32 * (1.0f32 - dist32 / 10.0f32);
        let expected_x = (0.1f32 + force32 * dx32 / dist32) as f64;
        let expected_y = (0.2f32 + force32 * dy32 / dist32) as f64;
        assert_eq!(x as f64, expected_x);
        assert_eq!(y as f64, expected_y);
    }

    #[cfg_attr(test, test)]
    fn congestion_fixed_components_untouched() {
        let positions = vec![10.0, 20.0, 100.0, 200.0];
        let fixed = vec![true, false];
        let b = vec![(10.0, 20.0)];
        let out = adjust_for_congestion(
            &positions,
            false,
            &fixed,
            &b,
            5.0,
            100.0,
            &|dx, dy| -> Result<f64, ()> {
                Ok((dx * dx + dy * dy).sqrt())
            },
            &|| Ok(1.0),
            &cos_sin,
        )
        .unwrap();
        assert_eq!(out[0], 10.0); // fixed component unchanged
        assert_eq!(out[1], 20.0);
    }

    #[cfg_attr(test, test)]
    fn congestion_outside_radius_is_noop() {
        let positions = vec![50.0, 50.0];
        let fixed = vec![false];
        let b = vec![(0.0, 0.0)]; // bottleneck far away
        let out = adjust_for_congestion(
            &positions,
            false,
            &fixed,
            &b,
            5.0,
            10.0, // influence radius only 10
            &|dx, dy| -> Result<f64, ()> {
                Ok((dx * dx + dy * dy).sqrt())
            },
            &|| Ok(1.0),
            &cos_sin,
        )
        .unwrap();
        // Distance from (50,50) to (0,0) is ~70.7 > 10, so no push.
        assert_eq!(out, vec![50.0, 50.0]);
    }

    // ---------- place_in_zone_center zone clamp --------------------------

    #[cfg_attr(test, test)]
    fn zone_center_clamps_to_bounds() {
        // A grid position outside the zone must be clamped.
        let refs: Vec<String> = (0..10).map(|i| format!("C{i}")).collect();
        let indices: Vec<Option<usize>> = refs.iter().enumerate().map(|(i, _)| Some(i)).collect();
        let (pos, _, _) =
            place_in_zone_center(10, &refs, &indices, 100.0, 100.0, (50.0, 50.0, 150.0, 150.0));
        for i in 0..10 {
            let x = pos[2 * i] as f64;
            let y = pos[2 * i + 1] as f64;
            assert!((50.0..=150.0).contains(&x), "x={x} outside zone for C{i}");
            assert!((50.0..=150.0).contains(&y), "y={y} outside zone for C{i}");
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("placer_core::placer_compute::tests::py_mod_floors_for_negative", py_mod_floors_for_negative),
        ("placer_core::placer_compute::tests::py_min_max_first_arg_on_tie_and_nan", py_min_max_first_arg_on_tie_and_nan),
        ("placer_core::placer_compute::tests::rotation_zero_is_identity", rotation_zero_is_identity),
        ("placer_core::placer_compute::tests::negative_rotation_composite_modulo", negative_rotation_composite_modulo),
        ("placer_core::placer_compute::tests::proximity_spiral_runs_without_zone", proximity_spiral_runs_without_zone),
        ("placer_core::placer_compute::tests::proximity_unknown_ref_unplaced", proximity_unknown_ref_unplaced),
        ("placer_core::placer_compute::tests::zone_center_grid_lays_out_around_center", zone_center_grid_lays_out_around_center),
        ("placer_core::placer_compute::tests::congestion_float64_normalized_push", congestion_float64_normalized_push),
        ("placer_core::placer_compute::tests::power_stage_duplicate_refs_resolve_to_last_index", power_stage_duplicate_refs_resolve_to_last_index),
        ("placer_core::placer_compute::tests::power_stage_duplicate_template_ref_last_geometry_wins", power_stage_duplicate_template_ref_last_geometry_wins),
        ("placer_core::placer_compute::tests::congestion_float32_chain_uses_f32_intermediates", congestion_float32_chain_uses_f32_intermediates),
        ("placer_core::placer_compute::tests::congestion_fixed_components_untouched", congestion_fixed_components_untouched),
        ("placer_core::placer_compute::tests::congestion_outside_radius_is_noop", congestion_outside_radius_is_noop),
        ("placer_core::placer_compute::tests::zone_center_clamps_to_bounds", zone_center_clamps_to_bounds),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(all(test, feature = "python"))]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    fn modulus() -> impl Strategy<Value = i64> {
        1i64..360i64
    }

    // ---------- py_max

    #[test]
    fn p18_py_max_returns_larger() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_max(a, b);
            let expected = a.max(b);
            prop_assert_eq!(r, expected);
        });
    }

    #[test]
    fn p19_py_max_returns_one_of_inputs() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_max(a, b);
            prop_assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits());
        });
    }

    #[test]
    fn p20_py_max_nan_first_returns_nan() {
        proptest!(|(b in normal())| {
            let nan = f64::NAN;
            prop_assert!(py_max(nan, b).is_nan());
        });
    }

    #[test]
    fn p21_py_max_nan_second_returns_first() {
        proptest!(|(a in normal())| {
            let nan = f64::NAN;
            prop_assert_eq!(py_max(a, nan), a);
        });
    }

    #[test]
    fn p22_py_max_signed_zero_first_wins() {
        assert_eq!(py_max(0.0, -0.0).to_bits(), 0.0f64.to_bits());
        assert_eq!(py_max(-0.0, 0.0).to_bits(), (-0.0f64).to_bits());
    }

    // ---------- py_min

    #[test]
    fn p23_py_min_returns_smaller() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_min(a, b);
            let expected = a.min(b);
            prop_assert_eq!(r, expected);
        });
    }

    #[test]
    fn p24_py_min_returns_one_of_inputs() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_min(a, b);
            prop_assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits());
        });
    }

    #[test]
    fn p25_py_min_nan_first_returns_nan() {
        proptest!(|(b in normal())| {
            prop_assert!(py_min(f64::NAN, b).is_nan());
        });
    }

    #[test]
    fn p26_py_min_nan_second_returns_first() {
        proptest!(|(a in normal())| {
            prop_assert_eq!(py_min(a, f64::NAN), a);
        });
    }

    #[test]
    fn p27_py_min_signed_zero_first_wins() {
        assert_eq!(py_min(0.0, -0.0).to_bits(), 0.0f64.to_bits());
        assert_eq!(py_min(-0.0, 0.0).to_bits(), (-0.0f64).to_bits());
    }

    // ---------- py_mod

    #[test]
    fn p28_py_mod_result_in_range() {
        proptest!(|(a in -10_000i64..10_000i64, b in modulus())| {
            let r = py_mod(a, b);
            prop_assert!(0 <= r && r < b);
        });
    }

    #[test]
    fn p29_py_mod_congruent() {
        proptest!(|(a in -10_000i64..10_000i64, b in modulus())| {
            let r = py_mod(a, b);
            prop_assert_eq!((a - r) % b, 0);
        });
    }

    #[test]
    fn p30_py_mod_idempotent() {
        proptest!(|(a in -10_000i64..10_000i64, b in modulus())| {
            let r = py_mod(a, b);
            prop_assert_eq!(py_mod(r, b), r);
        });
    }

    #[test]
    fn p31_py_mod_add_b_invariant() {
        proptest!(|(a in -10_000i64..10_000i64, b in modulus())| {
            prop_assume!(a <= 10_000 - b);
            prop_assert_eq!(py_mod(a + b, b), py_mod(a, b));
        });
    }
}
