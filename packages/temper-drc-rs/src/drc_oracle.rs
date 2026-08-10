//! `router_v6/constraints_drc_oracle.py::DRCOracle` — decision kernels,
//! ported from the pinned oracle
//! `packages/temper-placer/tests/router_v6/test_constraints_drc_oracle_rust_differential.py`
//! (whose `_oracle_*` block is the verbatim pre-migration module as of commit
//! `2e205228`, origin/main).
//!
//! The `DRCOracle` object itself stays Python: it is a stateful, pickled
//! `BoardState` field (`deterministic/state.py`), and its geometry lives in
//! `PCBGeometry` over the Python-visible `temper_geometry.RadiusIndex` R-tree.
//! Per the Wave-4 boundary (same as `clearance_matrix.rs`), the *spatial
//! queries* stay Python (they are the index's own result order, which the
//! oracle iterates in) and the *per-element numeric/decision bodies* move to
//! Rust as wire-format kernels. The Python shim marshals the query results
//! in index order, so the kernels' first-violation short-circuit is the
//! oracle's.
//!
//! Ported:
//! - [`severity`] — `Violation.severity` (`0.0 if required <= 0 else
//!   1.0 - (actual / required)`).
//! - [`pad_credit`] / [`effective_clearance`] — the `@req(2026-06-23-007,
//!   R3)` spatially-scoped clearance-credit kernels
//!   (`get_pad_credit` / `get_effective_clearance`): per-credit comp/pin
//!   match in *insertion order* (first match wins), then the axis-gated
//!   AABB band test.
//! - [`can_place_via`] — `can_place_via`: search-radius arithmetic is the
//!   query glue (Python), the per-item neckdown `min`, effective-clearance
//!   addition, distance, and strict-`<` comparison are here.
//! - [`can_place_track`] — `can_place_track_segment`: same shape plus the
//!   companion-net skip, the R3 credit stack, the EXP-13 internal-layer
//!   creepage factor (`required > 0.5` gate, then `* 0.30`), and the
//!   `- 0.001` segment-track tolerance.
//! - [`validate_all`] — `validate_all`'s four pairwise checks (track-track
//!   with `- 0.010` tolerance, via-via, track-pad, via-pad).  The Python
//!   shim enumerates the pairs (spatial query + id/net/diff-pair filters +
//!   per-pair `get_clearance`), passing them as record pyclasses; the kernel
//!   does the effective/actual arithmetic and emits violations in the
//!   oracle's emission order.
//!
//! NOT ported (all recorded in the differential's module docstring):
//! `register_track(s)`/`register_via(s)`/`register_pad(s)`/`clear` (pure
//! `PCBGeometry` glue), `add_clearance_credit` (axis validation + dict
//! insert), `_resolve_owner` (`pin_owner` may be a callable),
//! `get_valid_via_sites` (grid loop + Python sort key), and the f-string
//! `reason` message formatting (R1a: `str(float)`/`{:.3f}` rendering is a
//! Python library semantic; the kernels return the structured violation and
//! the shim builds the message from the same Python code the oracle ran).
//!
//! # Bit-exactness notes
//!
//! - The three distance primitives are the *same* `temper-geometry`
//!   `drc_constraints_geometry` functions the Python arm delegates to, so
//!   bit-exactness is by construction; `Via`-center distance
//!   (`p_center.distance_to`) is `math.hypot` → [`crate::pymath::py_hypot`].
//! - `min(required, 0.08)` under `neckdown` is CPython builtin `min`
//!   (first-arg wins on NaN) → [`crate::pymath::py_min`], never `f64::min`
//!   (B5).  The differential's `test_can_place_neckdown_keeps_nan` pins the
//!   discriminating geometry.
//! - Arithmetic grouping is preserved verbatim: `required + via_radius +
//!   (track.width / 2)` evaluates as `(required + via_radius) + (width/2)`,
//!   `required * 0.30` is one multiply by the double `0.30`, and the
//!   tolerance subtractions `effective - 0.001` / `effective - 0.010` are
//!   the oracle's exact expressions (B7).
//! - The credit AABB comparisons are plain f64 `<=` chains (CPython chained
//!   comparison == short-circuit `&&`), so a NaN never enters the band.
//! - The R3 set equality `{pin_a, pin_b} != {c_lv, c_hv}` is replicated as
//!   genuine 2-element *set* equality (singleton collapse included).
//!
//! # Panic policy (R1g)
//!
//! pyo3 wraps every `#[pyfunction]` boundary in its default `catch_unwind`;
//! a Rust panic surfaces as `pyo3_runtime.PanicException`, never across the
//! boundary as UB.  No `unwrap`/`expect` outside `#[cfg(test)]` (crate
//! clippy lint).

use pyo3::prelude::*;
use pyo3::types::PyModule;

use temper_geometry::drc_constraints_geometry::{
    point_to_rotated_rect_distance, point_to_segment_distance,
    segment_to_rotated_rect_distance, segment_to_segment_distance,
};

use crate::pymath::{py_hypot, py_min};

/// `INTERNAL_LAYER_CREEPAGE_FACTOR` — the EXP-13 factor, as the double the
/// Python module names `0.30`.
const INTERNAL_LAYER_CREEPAGE_FACTOR: f64 = 0.30;

/// `min(required, 0.08)` — the `neckdown` relaxation.  CPython builtin
/// `min`: first argument survives a NaN (B5); `f64::min` would discard it.
#[inline]
fn neckdown_required(required: f64, neckdown: bool) -> f64 {
    if neckdown {
        py_min(required, 0.08)
    } else {
        required
    }
}

/// Set equality of two Python-2-element `set`s (R3 pin pair check).  Python
/// `{a, b} != {c, d}` compares the *sets*, so `("1","1") == ("1","1")` (both
/// collapse to singletons) and `("1","1") != ("1","2")`, even though the
/// raw tuples differ pairwise.  `{pin_a, pin_b} != {c_lv, c_hv}`:
///
/// - both singletons: equal iff the elements are equal;
/// - one singleton, one pair: unequal;
/// - two pairs: equal iff `(a==c && b==d) || (a==d && b==c)`.
fn set2_eq(a1: &str, a2: &str, b1: &str, b2: &str) -> bool {
    let a_singleton = a1 == a2;
    let b_singleton = b1 == b2;
    if a_singleton || b_singleton {
        return a_singleton && b_singleton && a1 == b1;
    }
    (a1 == b1 && a2 == b2) || (a1 == b2 && a2 == b1)
}

// ---------------------------------------------------------------------------
// Violation.severity
// ---------------------------------------------------------------------------

/// `Violation.severity`: `0.0 if clearance_required <= 0 else 1.0 -
/// (clearance_actual / clearance_required)`.  A NaN `clearance_required`
/// fails `<= 0` and flows into the division, exactly as Python's conditional
/// does.
pub fn severity(clearance_actual: f64, clearance_required: f64) -> f64 {
    if clearance_required <= 0.0 {
        0.0
    } else {
        1.0 - (clearance_actual / clearance_required)
    }
}

#[pyfunction]
pub fn drc_oracle_severity_py(clearance_actual: f64, clearance_required: f64) -> f64 {
    severity(clearance_actual, clearance_required)
}

// ---------------------------------------------------------------------------
// Clearance credits (R3): get_pad_credit / get_effective_clearance
// ---------------------------------------------------------------------------

/// One registered clearance credit, marshalled in `clearance_credits`
/// *insertion order* (the oracle iterates `dict.items()`, first match wins):
/// `(comp_ref, c_lv, c_hv, effective, hw, hl, smx, smy, axis)`.
type CreditWire = (
    String,
    String,
    String,
    f64,
    f64,
    f64,
    f64,
    f64,
    Option<String>,
);

/// The axis-gated band test shared by both credit kernels.  `points` is the
/// one or two pad centers under test; `inside_x`/`inside_y` mirror the
/// oracle's two AABB orientations verbatim (`half_w_band = hw + 0.5`).
fn inside_band(hw: f64, hl: f64, smx: f64, smy: f64, axis: &Option<String>, points: &[(f64, f64)]) -> bool {
    let half_w_band = hw + 0.5;
    let inside_x = points.iter().all(|(px, py)| {
        (smx - half_w_band <= *px && *px <= smx + half_w_band) && (smy - hl <= *py && *py <= smy + hl)
    });
    let inside_y = points.iter().all(|(px, py)| {
        (smx - hl <= *px && *px <= smx + hl) && (smy - half_w_band <= *py && *py <= smy + half_w_band)
    });
    match axis {
        Some(a) if a == "x" => inside_x,
        Some(a) if a == "y" => inside_y,
        _ => inside_x || inside_y,
    }
}

/// `DRCOracle.get_pad_credit` — the effective clearance credited to a single
/// pad inside a slot's reclaimed band, or `None`.  `owner`/`pin` are already
/// resolved by the Python shim (`_resolve_owner` + the `{ref}-{pin}` split
/// stay Python: `pin_owner` may be a callable).
pub fn pad_credit(
    owner: &str,
    pin: &str,
    px: f64,
    py: f64,
    credits: &[CreditWire],
) -> Option<f64> {
    for (comp_ref, c_lv, c_hv, effective, hw, hl, smx, smy, axis) in credits {
        if comp_ref != owner {
            continue;
        }
        if pin != c_lv && pin != c_hv {
            continue;
        }
        if inside_band(*hw, *hl, *smx, *smy, axis, &[(px, py)]) {
            return Some(*effective);
        }
    }
    None
}

#[pyfunction]
pub fn drc_oracle_pad_credit_py(
    owner: String,
    pin: String,
    px: f64,
    py: f64,
    credits: Vec<CreditWire>,
) -> Option<f64> {
    pad_credit(&owner, &pin, px, py, &credits)
}

/// `DRCOracle.get_effective_clearance` — the credited clearance for a
/// (pad_a, pad_b) pair on the same component, or `None`.
#[allow(clippy::too_many_arguments)]
pub fn effective_clearance(
    owner: &str,
    pin_a: &str,
    ax: f64,
    ay: f64,
    pin_b: &str,
    bx: f64,
    by: f64,
    credits: &[CreditWire],
) -> Option<f64> {
    for (comp_ref, c_lv, c_hv, effective, hw, hl, smx, smy, axis) in credits {
        if comp_ref != owner {
            continue;
        }
        if !set2_eq(pin_a, pin_b, c_lv, c_hv) {
            continue;
        }
        if inside_band(*hw, *hl, *smx, *smy, axis, &[(ax, ay), (bx, by)]) {
            return Some(*effective);
        }
    }
    None
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_oracle_effective_clearance_py(
    owner: String,
    pin_a: String,
    ax: f64,
    ay: f64,
    pin_b: String,
    bx: f64,
    by: f64,
    credits: Vec<CreditWire>,
) -> Option<f64> {
    effective_clearance(&owner, &pin_a, ax, ay, &pin_b, bx, by, &credits)
}

// ---------------------------------------------------------------------------
// can_place_via
// ---------------------------------------------------------------------------

/// `(id, net, width, x1, y1, x2, y2, required)` — one nearby track, `required`
/// already resolved by the shim's `rules.get_clearance(net, track.net, x, y)`.
type NearTrackWire = (String, String, f64, f64, f64, f64, f64, f64);

/// `(id, net, mask_expansion, cx, cy, w, h, rotation, required)` — one
/// nearby pad.
type NearPadViaWire = (String, String, f64, f64, f64, f64, f64, f64, f64);

/// `(id, net, diameter, cx, cy, required)` — one nearby via.
type NearViaWire = (String, String, f64, f64, f64, f64);

/// `can_place_via`'s loop bodies.  Returns the first violation in marshalled
/// (i.e. spatial-index query) order as `(kind, id, actual, effective)`, or
/// `None`.  The message strings are built in Python.
#[allow(clippy::too_many_arguments)]
pub fn can_place_via(
    x: f64,
    y: f64,
    via_radius: f64,
    net: &str,
    neckdown: bool,
    tracks: &[NearTrackWire],
    pads: &[NearPadViaWire],
    vias: &[NearViaWire],
) -> Option<(String, String, f64, f64)> {
    for (id, tnet, tw, x1, y1, x2, y2, required) in tracks {
        if tnet == net {
            continue;
        }
        let required = neckdown_required(*required, neckdown);
        let effective = required + via_radius + (tw / 2.0);
        let actual = point_to_segment_distance(x, y, *x1, *y1, *x2, *y2);
        if actual < effective {
            return Some(("track".to_string(), id.clone(), actual, effective));
        }
    }

    for (id, pnet, mask, cx, cy, w, h, rotation, required) in pads {
        if pnet == net {
            continue;
        }
        let required = neckdown_required(*required, neckdown);
        let effective = required + via_radius + mask;
        let actual = point_to_rotated_rect_distance(x, y, *cx, *cy, *w, *h, *rotation);
        if actual < effective {
            return Some(("pad".to_string(), id.clone(), actual, effective));
        }
    }

    for (id, vnet, diameter, cx, cy, required) in vias {
        if vnet == net {
            continue;
        }
        let required = neckdown_required(*required, neckdown);
        let effective = required + via_radius + (diameter / 2.0);
        let actual = py_hypot(x - cx, y - cy);
        if actual < effective {
            return Some(("via".to_string(), id.clone(), actual, effective));
        }
    }

    None
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_oracle_can_place_via_py(
    x: f64,
    y: f64,
    via_radius: f64,
    net: String,
    neckdown: bool,
    tracks: Vec<NearTrackWire>,
    pads: Vec<NearPadViaWire>,
    vias: Vec<NearViaWire>,
) -> Option<(String, String, f64, f64)> {
    can_place_via(x, y, via_radius, &net, neckdown, &tracks, &pads, &vias)
}

// ---------------------------------------------------------------------------
// can_place_track_segment
// ---------------------------------------------------------------------------

/// `(id, net, mask_expansion, is_pth, cx, cy, w, h, rotation, credit,
/// required)` — one nearby pad.  `credit` is the shim's pre-resolved
/// `get_pad_credit(pad)` (itself a Rust kernel), `None` when no credit
/// applies.
type NearPadTrackWire = (
    String,
    String,
    f64,
    bool,
    f64,
    f64,
    f64,
    f64,
    f64,
    Option<f64>,
    f64,
);

/// `can_place_track_segment`'s loop bodies.  `apply_internal_creepage` is
/// the Python-evaluated `enable_internal_layer_creepage && LayerIndex(layer)
/// in INTERNAL_LAYERS` (the `LayerIndex` IntEnum stays Python).
#[allow(clippy::too_many_arguments)]
pub fn can_place_track(
    sx: f64,
    sy: f64,
    ex: f64,
    ey: f64,
    net: &str,
    width: f64,
    neckdown: bool,
    companion_net: &Option<String>,
    apply_internal_creepage: bool,
    tracks: &[NearTrackWire],
    pads: &[NearPadTrackWire],
    vias: &[NearViaWire],
) -> Option<(String, String, f64, f64)> {
    for (id, tnet, tw, x1, y1, x2, y2, required) in tracks {
        if tnet == net {
            continue;
        }
        if let Some(c) = companion_net && tnet == c {
            continue;
        }
        let required = neckdown_required(*required, neckdown);
        let effective = required + (width / 2.0) + (tw / 2.0);
        let actual = segment_to_segment_distance(sx, sy, ex, ey, *x1, *y1, *x2, *y2);
        // Allow 1µm tolerance for floating point precision.
        if actual < effective - 0.001 {
            return Some(("track".to_string(), id.clone(), actual, effective));
        }
    }

    for (id, pnet, mask, is_pth, cx, cy, w, h, rotation, credit, required) in pads {
        if pnet == net {
            continue;
        }
        if let Some(c) = companion_net && pnet == c {
            continue;
        }
        let mut required = neckdown_required(*required, neckdown);
        // R3: credit stacks onto the baseline when smaller.
        if let Some(credit) = credit && *credit < required {
            required = *credit;
        }
        // EXP-13: internal-layer creepage reduction for PTH pads, gated on
        // required > 0.5 (only creepage requirements shrink, not basic
        // clearance).
        if apply_internal_creepage && *is_pth && required > 0.5 {
            required *= INTERNAL_LAYER_CREEPAGE_FACTOR;
        }
        let effective = required + (width / 2.0) + mask;
        let actual = segment_to_rotated_rect_distance(sx, sy, ex, ey, *cx, *cy, *w, *h, *rotation);
        if actual < effective {
            return Some(("pad".to_string(), id.clone(), actual, effective));
        }
    }

    for (id, vnet, diameter, cx, cy, required) in vias {
        if vnet == net {
            continue;
        }
        if let Some(c) = companion_net && vnet == c {
            continue;
        }
        let required = neckdown_required(*required, neckdown);
        let effective = required + (width / 2.0) + (diameter / 2.0);
        let actual = point_to_segment_distance(*cx, *cy, sx, sy, ex, ey);
        if actual < effective {
            return Some(("via".to_string(), id.clone(), actual, effective));
        }
    }

    None
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_oracle_can_place_track_py(
    sx: f64,
    sy: f64,
    ex: f64,
    ey: f64,
    net: String,
    width: f64,
    neckdown: bool,
    companion_net: Option<String>,
    apply_internal_creepage: bool,
    tracks: Vec<NearTrackWire>,
    pads: Vec<NearPadTrackWire>,
    vias: Vec<NearViaWire>,
) -> Option<(String, String, f64, f64)> {
    can_place_track(
        sx, sy, ex, ey, &net, width, neckdown, &companion_net,
        apply_internal_creepage, &tracks, &pads, &vias,
    )
}

// ---------------------------------------------------------------------------
// validate_all
// ---------------------------------------------------------------------------

/// Record pyclasses for `validate_all`'s four pairwise checks.  The Python
/// shim enumerates the pairs (spatial query order + id/net/diff-pair filters
/// + per-pair `required`), and the kernel performs the effective/actual
/// arithmetic, the comparison, and the violation-record emission.  Plain
/// data carriers with `#[pyo3(get)]` fields.

#[pyclass]
pub struct DrcOracleTrackPair {
    #[pyo3(get)]
    pub id_a: String,
    #[pyo3(get)]
    pub net_a: String,
    #[pyo3(get)]
    pub w_a: f64,
    #[pyo3(get)]
    pub sx_a: f64,
    #[pyo3(get)]
    pub sy_a: f64,
    #[pyo3(get)]
    pub ex_a: f64,
    #[pyo3(get)]
    pub ey_a: f64,
    #[pyo3(get)]
    pub id_b: String,
    #[pyo3(get)]
    pub net_b: String,
    #[pyo3(get)]
    pub w_b: f64,
    #[pyo3(get)]
    pub sx_b: f64,
    #[pyo3(get)]
    pub sy_b: f64,
    #[pyo3(get)]
    pub ex_b: f64,
    #[pyo3(get)]
    pub ey_b: f64,
    #[pyo3(get)]
    pub required: f64,
}

#[pymethods]
impl DrcOracleTrackPair {
    #[new]
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id_a: String,
        net_a: String,
        w_a: f64,
        sx_a: f64,
        sy_a: f64,
        ex_a: f64,
        ey_a: f64,
        id_b: String,
        net_b: String,
        w_b: f64,
        sx_b: f64,
        sy_b: f64,
        ex_b: f64,
        ey_b: f64,
        required: f64,
    ) -> Self {
        Self {
            id_a,
            net_a,
            w_a,
            sx_a,
            sy_a,
            ex_a,
            ey_a,
            id_b,
            net_b,
            w_b,
            sx_b,
            sy_b,
            ex_b,
            ey_b,
            required,
        }
    }
}

#[pyclass]
pub struct DrcOracleViaPair {
    #[pyo3(get)]
    pub id_a: String,
    #[pyo3(get)]
    pub net_a: String,
    #[pyo3(get)]
    pub d_a: f64,
    #[pyo3(get)]
    pub ax: f64,
    #[pyo3(get)]
    pub ay: f64,
    #[pyo3(get)]
    pub id_b: String,
    #[pyo3(get)]
    pub net_b: String,
    #[pyo3(get)]
    pub d_b: f64,
    #[pyo3(get)]
    pub bx: f64,
    #[pyo3(get)]
    pub by: f64,
    #[pyo3(get)]
    pub required: f64,
}

#[pymethods]
impl DrcOracleViaPair {
    #[new]
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id_a: String,
        net_a: String,
        d_a: f64,
        ax: f64,
        ay: f64,
        id_b: String,
        net_b: String,
        d_b: f64,
        bx: f64,
        by: f64,
        required: f64,
    ) -> Self {
        Self {
            id_a,
            net_a,
            d_a,
            ax,
            ay,
            id_b,
            net_b,
            d_b,
            bx,
            by,
            required,
        }
    }
}

#[pyclass]
pub struct DrcOracleTrackPadPair {
    #[pyo3(get)]
    pub t_id: String,
    #[pyo3(get)]
    pub t_net: String,
    #[pyo3(get)]
    pub t_w: f64,
    #[pyo3(get)]
    pub tsx: f64,
    #[pyo3(get)]
    pub tsy: f64,
    #[pyo3(get)]
    pub tex: f64,
    #[pyo3(get)]
    pub tey: f64,
    #[pyo3(get)]
    pub p_id: String,
    #[pyo3(get)]
    pub p_net: String,
    #[pyo3(get)]
    pub p_mask: f64,
    #[pyo3(get)]
    pub p_cx: f64,
    #[pyo3(get)]
    pub p_cy: f64,
    #[pyo3(get)]
    pub p_w: f64,
    #[pyo3(get)]
    pub p_h: f64,
    #[pyo3(get)]
    pub p_rot: f64,
    #[pyo3(get)]
    pub required: f64,
}

#[pymethods]
impl DrcOracleTrackPadPair {
    #[new]
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        t_id: String,
        t_net: String,
        t_w: f64,
        tsx: f64,
        tsy: f64,
        tex: f64,
        tey: f64,
        p_id: String,
        p_net: String,
        p_mask: f64,
        p_cx: f64,
        p_cy: f64,
        p_w: f64,
        p_h: f64,
        p_rot: f64,
        required: f64,
    ) -> Self {
        Self {
            t_id,
            t_net,
            t_w,
            tsx,
            tsy,
            tex,
            tey,
            p_id,
            p_net,
            p_mask,
            p_cx,
            p_cy,
            p_w,
            p_h,
            p_rot,
            required,
        }
    }
}

#[pyclass]
pub struct DrcOracleViaPadPair {
    #[pyo3(get)]
    pub v_id: String,
    #[pyo3(get)]
    pub v_net: String,
    #[pyo3(get)]
    pub v_d: f64,
    #[pyo3(get)]
    pub vx: f64,
    #[pyo3(get)]
    pub vy: f64,
    #[pyo3(get)]
    pub p_id: String,
    #[pyo3(get)]
    pub p_net: String,
    #[pyo3(get)]
    pub p_mask: f64,
    #[pyo3(get)]
    pub p_cx: f64,
    #[pyo3(get)]
    pub p_cy: f64,
    #[pyo3(get)]
    pub p_w: f64,
    #[pyo3(get)]
    pub p_h: f64,
    #[pyo3(get)]
    pub p_rot: f64,
    #[pyo3(get)]
    pub required: f64,
}

#[pymethods]
impl DrcOracleViaPadPair {
    #[new]
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        v_id: String,
        v_net: String,
        v_d: f64,
        vx: f64,
        vy: f64,
        p_id: String,
        p_net: String,
        p_mask: f64,
        p_cx: f64,
        p_cy: f64,
        p_w: f64,
        p_h: f64,
        p_rot: f64,
        required: f64,
    ) -> Self {
        Self {
            v_id,
            v_net,
            v_d,
            vx,
            vy,
            p_id,
            p_net,
            p_mask,
            p_cx,
            p_cy,
            p_w,
            p_h,
            p_rot,
            required,
        }
    }
}

/// A `validate_all` violation record: `(type, geometry_a_id, geometry_b_id,
/// net_a, net_b, clearance_actual, clearance_required, location_x,
/// location_y)`.  The Python shim wraps it in the `Violation` dataclass.
pub type ViolationRecord = (
    String,
    String,
    String,
    String,
    String,
    f64,
    f64,
    f64,
    f64,
);

/// `validate_all`'s four pairwise checks, in the oracle's emission order
/// (track-track, via-via, track-pad, via-pad).  The pair lists arrive
/// pre-enumerated by the shim, preserving the spatial-index query order and
/// the `track_a.id >= track_b.id` / net / diff-pair filters.
pub fn validate_all(
    track_pairs: &[&DrcOracleTrackPair],
    via_pairs: &[&DrcOracleViaPair],
    track_pad_pairs: &[&DrcOracleTrackPadPair],
    via_pad_pairs: &[&DrcOracleViaPadPair],
) -> Vec<ViolationRecord> {
    let mut out = Vec::new();

    for p in track_pairs {
        let effective = p.required + (p.w_a / 2.0) + (p.w_b / 2.0);
        let actual = segment_to_segment_distance(
            p.sx_a, p.sy_a, p.ex_a, p.ey_a, p.sx_b, p.sy_b, p.ex_b, p.ey_b,
        );
        // Allow 10µm tolerance for floating point precision and
        // manufacturing variation.
        if actual < effective - 0.010 {
            out.push((
                "track_clearance".to_string(),
                p.id_a.clone(),
                p.id_b.clone(),
                p.net_a.clone(),
                p.net_b.clone(),
                actual,
                effective,
                (p.sx_a + p.ex_a) / 2.0,
                (p.sy_a + p.ey_a) / 2.0,
            ));
        }
    }

    for p in via_pairs {
        let effective = p.required + (p.d_a / 2.0) + (p.d_b / 2.0);
        let actual = py_hypot(p.ax - p.bx, p.ay - p.by);
        if actual < effective {
            out.push((
                "via_to_via".to_string(),
                p.id_a.clone(),
                p.id_b.clone(),
                p.net_a.clone(),
                p.net_b.clone(),
                actual,
                effective,
                p.ax,
                p.ay,
            ));
        }
    }

    for p in track_pad_pairs {
        let effective = p.required + (p.t_w / 2.0) + p.p_mask;
        let actual = segment_to_rotated_rect_distance(
            p.tsx, p.tsy, p.tex, p.tey, p.p_cx, p.p_cy, p.p_w, p.p_h, p.p_rot,
        );
        if actual < effective {
            out.push((
                "track_pad_clearance".to_string(),
                p.t_id.clone(),
                p.p_id.clone(),
                p.t_net.clone(),
                p.p_net.clone(),
                actual,
                effective,
                (p.tsx + p.tex) / 2.0,
                (p.tsy + p.tey) / 2.0,
            ));
        }
    }

    for p in via_pad_pairs {
        let effective = p.required + (p.v_d / 2.0) + p.p_mask;
        let actual = point_to_rotated_rect_distance(
            p.vx, p.vy, p.p_cx, p.p_cy, p.p_w, p.p_h, p.p_rot,
        );
        if actual < effective {
            out.push((
                "via_pad_clearance".to_string(),
                p.v_id.clone(),
                p.p_id.clone(),
                p.v_net.clone(),
                p.p_net.clone(),
                actual,
                effective,
                p.vx,
                p.vy,
            ));
        }
    }

    out
}

#[pyfunction]
pub fn drc_oracle_validate_all_py(
    py: Python<'_>,
    track_pairs: Vec<Py<DrcOracleTrackPair>>,
    via_pairs: Vec<Py<DrcOracleViaPair>>,
    track_pad_pairs: Vec<Py<DrcOracleTrackPadPair>>,
    via_pad_pairs: Vec<Py<DrcOracleViaPadPair>>,
) -> PyResult<Vec<ViolationRecord>> {
    let tp: Vec<PyRef<'_, DrcOracleTrackPair>> =
        track_pairs.iter().map(|p| p.bind(py).borrow()).collect();
    let vp: Vec<PyRef<'_, DrcOracleViaPair>> =
        via_pairs.iter().map(|p| p.bind(py).borrow()).collect();
    let tpp: Vec<PyRef<'_, DrcOracleTrackPadPair>> =
        track_pad_pairs.iter().map(|p| p.bind(py).borrow()).collect();
    let vpp: Vec<PyRef<'_, DrcOracleViaPadPair>> =
        via_pad_pairs.iter().map(|p| p.bind(py).borrow()).collect();
    let tp: Vec<&DrcOracleTrackPair> = tp.iter().map(|r| &**r).collect();
    let vp: Vec<&DrcOracleViaPair> = vp.iter().map(|r| &**r).collect();
    let tpp: Vec<&DrcOracleTrackPadPair> = tpp.iter().map(|r| &**r).collect();
    let vpp: Vec<&DrcOracleViaPadPair> = vpp.iter().map(|r| &**r).collect();
    Ok(validate_all(&tp, &vp, &tpp, &vpp))
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(drc_oracle_severity_py, module)?)?;
    module.add_function(wrap_pyfunction!(drc_oracle_pad_credit_py, module)?)?;
    module.add_function(wrap_pyfunction!(drc_oracle_effective_clearance_py, module)?)?;
    module.add_function(wrap_pyfunction!(drc_oracle_can_place_via_py, module)?)?;
    module.add_function(wrap_pyfunction!(drc_oracle_can_place_track_py, module)?)?;
    module.add_function(wrap_pyfunction!(drc_oracle_validate_all_py, module)?)?;
    module.add_class::<DrcOracleTrackPair>()?;
    module.add_class::<DrcOracleViaPair>()?;
    module.add_class::<DrcOracleTrackPadPair>()?;
    module.add_class::<DrcOracleViaPadPair>()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests (Rust-side; the Python differential is the primary proof)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn severity_formula_matches_oracle() {
        assert_eq!(severity(1.0, 2.0), 0.5);
        assert_eq!(severity(2.0, 1.0), -1.0);
        assert_eq!(severity(0.0, 2.0), 1.0);
        assert_eq!(severity(1.0, 0.0), 0.0);
        assert_eq!(severity(3.0, -1.0), 0.0);
        assert!(severity(1.0, f64::NAN).is_nan());
        assert!(severity(f64::NAN, 2.0).is_nan());
    }

    #[test]
    fn neckdown_min_keeps_first_nan() {
        // CPython `min(NaN, 0.08)` == NaN; `f64::min` would give 0.08.
        assert!(neckdown_required(f64::NAN, true).is_nan());
        assert_eq!(neckdown_required(0.2, true), 0.08);
        assert_eq!(neckdown_required(0.05, true), 0.05);
        assert_eq!(neckdown_required(0.2, false), 0.2);
    }

    #[test]
    fn set2_eq_replicates_python_set_semantics() {
        assert!(set2_eq("1", "2", "1", "2"));
        assert!(set2_eq("1", "2", "2", "1"));
        assert!(!set2_eq("1", "2", "1", "3"));
        // singletons collapse: {"1","1"} == {"1","1"}
        assert!(set2_eq("1", "1", "1", "1"));
        assert!(!set2_eq("1", "1", "1", "2"));
        assert!(!set2_eq("1", "2", "1", "1"));
    }

    #[test]
    fn pad_credit_axis_gate() {
        let credits = vec![(
            "Q1".to_string(),
            "1".to_string(),
            "2".to_string(),
            5.2,
            1.0,
            3.0,
            10.0,
            10.0,
            Some("x".to_string()),
        )];
        // inside the x band
        assert_eq!(pad_credit("Q1", "1", 10.0, 10.0, &credits), Some(5.2));
        // outside x band -> None
        assert_eq!(pad_credit("Q1", "1", 13.1, 10.0, &credits), None);
        // wrong pin -> None
        assert_eq!(pad_credit("Q1", "3", 10.0, 10.0, &credits), None);
        // wrong owner -> None
        assert_eq!(pad_credit("Q2", "1", 10.0, 10.0, &credits), None);
    }

    #[test]
    fn effective_clearance_rejects_cross_component() {
        let credits = vec![(
            "Q1".to_string(),
            "1".to_string(),
            "2".to_string(),
            5.2,
            1.0,
            3.0,
            10.0,
            10.0,
            None,
        )];
        assert_eq!(
            effective_clearance("Q1", "1", 10.0, 10.0, "2", 10.0, 11.0, &credits),
            Some(5.2)
        );
        // reversed pin order (set equality)
        assert_eq!(
            effective_clearance("Q1", "2", 10.0, 11.0, "1", 10.0, 10.0, &credits),
            Some(5.2)
        );
        assert_eq!(
            effective_clearance("Q2", "1", 10.0, 10.0, "2", 10.0, 11.0, &credits),
            None
        );
    }
}
