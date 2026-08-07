//! Wave 4 cluster D — the `router_v6` post-route DFM kernels.
//!
//! Bit-exact ports of the compute kernels of seven
//! `temper_placer/router_v6` modules, pinned verbatim by
//! `packages/temper-placer/tests/router_v6/_dfm_py_oracle.py` and compared
//! by type-carrying signature (no tolerance) by
//! `test_dfm_rust_differential.py`. `REQUIRED_RUST_SYMBOLS` in that file
//! is the contract; each symbol's call shape is fixed by the test that
//! calls it. The pyo3 boundary lives in [`crate::dfm_py`] — this module is
//! deliberately free of `pyo3` so `cargo test --no-default-features` can
//! run every kernel (the crate's `cdylib` + `extension-module` build
//! cannot link a test binary).
//!
//! | Python origin | kernels here |
//! |---|---|
//! | `thermal_relief` | [`is_power_net`], [`connects_to_power_plane`], [`generate_spoke_segments`], [`clamp_to_rect_outline`] |
//! | `acid_trap_detection` | [`calculate_angle`], [`classify_severity`] |
//! | `power_plane` | [`board_bounds`], [`rect_polygon`], [`power_pour_bounds`], [`thermal_via_positions`] |
//! | `copper_balance` | [`via_annular_area`], [`layer_is_between`], [`segment_run_copper_area`] |
//! | `via_placement` | [`via_segment_index`], [`adjacent_layer`] |
//! | `annular_ring_check` | [`check_annular_ring`] |
//! | `teardrop_generation` | [`via_teardrop`] |
//!
//! # What is deliberately NOT here
//!
//! - **`_clamp_to_board_outline`'s polygonal arm.** It is
//!   `shapely.Polygon.contains` / `.touches` / `.intersection(LineString)`
//!   — GEOS predicate and boolean results, a distinct oracle with no Rust
//!   replication on the table (contract B6, survey spike S1). Only the
//!   rectangular fast path is ported; the arm stays Python and is proved
//!   reachable by
//!   `test_polygonal_clamp_arm_is_out_of_scope_and_is_a_geos_oracle`.
//! - **`thermal_relief._add_smd_thermal_reliefs`.** It iterates a
//!   `frozenset[str]`, whose order CPython randomizes per process (oracle
//!   defect D1). It has no bit-exact contract to port, and sorting it here
//!   to make the arms agree would be an undetectable behaviour change.
//! - **The orchestrators** (`check_*` / `add_*` / `detect_*`) — they take
//!   a `RoutingResults`, which is not a pyclass yet.
//! - **`_extract_2d_coordinates`** — pure attribute plumbing whose
//!   contract is the `AttributeError` it raises; it stays in the shim.
//!
//! # Floating-point rules this module obeys
//!
//! Everything numeric goes through [`crate::pymath`], which documents the
//! divergence class it closes. Three rules are specific to this cluster
//! and easy to get backwards:
//!
//! 1. `acid_trap_detection` computes `sqrt(x ** 2 + y ** 2)`, which is
//!    **neither** `math.hypot` (17.3% of random 2-vectors disagree)
//!    **nor** `x * x` (0.105% of random f64). `copper_balance` and
//!    `teardrop_generation` *do* use `math.hypot`, and
//!    [`via_annular_area`] *does* use `r * r`. They are different
//!    expressions and are not unified.
//! 2. `angle = 2.0 * pi * i / spoke_count` is a left-to-right chain.
//!    Regrouping that keeps `pi * i` before the divide is exact;
//!    regrouping that moves the divide first changes 27% of `(i, n)`
//!    pairs. The spelling here keeps the chain.
//! 3. `round(angle_deg, 9)` is decimal round-half-even and is
//!    load-bearing: the exact 60-degree vertex is `59.99999999999999`
//!    before the round and `60.0` after, which flips the severity band.

use std::sync::OnceLock;

use crate::pymath;

// ---------------------------------------------------------------------------
// Errors the kernels can raise (rendered into Python exceptions by `dfm_py`)
// ---------------------------------------------------------------------------

/// The exceptions the shipped kernels raise, carried structurally so the
/// pyo3 boundary can render the message with CPython's own `str()` —
/// `str(float)` is shortest-repr with scientific notation below `1e-4` and
/// at/above `1e16`, which Rust's `Display` does not reproduce.
///
/// The differential compares raised exceptions as values (type **and**
/// message), so these are contract, not diagnostics.
#[derive(Clone, Debug, PartialEq)]
pub enum DfmError {
    /// `ValueError(f"isolation_gap_mm must be >= 0, got {gap}")`
    NegativeIsolationGap { gap: PyNum },
    /// `ValueError(f"Board too narrow ({w}mm) for {n} isolated pours with {gap}mm gaps")`
    BoardTooNarrow { total_width: PyNum, n: usize, gap: PyNum },
    /// `ValueError(f"count must be a perfect square, got {count}")`
    NotAPerfectSquare { count: i64 },
    /// `TypeError("type complex doesn't define __round__ method")` —
    /// `(-1) ** 0.5` is a complex, and `round` has no complex overload.
    ComplexRound,
    /// This port carries Python `int` as `i64`; see [`PyNum`].
    IntOverflow,
    /// `OverflowError(ERANGE, strerror(ERANGE))` — CPython's
    /// `float.__pow__` raises when the result overflows to infinity.
    /// [`calculate_angle`]'s `x ** 2` reaches it from the corpus's
    /// `1e200` and `f64::MAX` rows.
    PowOverflow,
    /// The flattened (parallel-slice) call shape was handed ragged lists.
    RaggedInput(&'static str),
}

type DfmResult<T> = Result<T, DfmError>;

// ---------------------------------------------------------------------------
// CPython's numeric tower, for the kernels whose output type depends on it
// ---------------------------------------------------------------------------

/// A Python `int` or `float`, kept apart because the differential compares
/// by *type-carrying* signature.
///
/// [`board_bounds`], [`rect_polygon`] and [`clamp_to_rect_outline`]
/// perform no float-only arithmetic: given `int` inputs they return
/// `int`s, and `sig()` separates `('int', 0)` from `('float', '0x0p+0')`.
/// A kernel that widened everything to `f64` would fail the differential
/// on exactly the corpus rows that were added to catch it (`_dfm_cases.py`
/// marks them `# integers (int/float divergence in the signature
/// comparator)`), so the two-type numeric tower is implemented rather than
/// flattened.
///
/// Known narrowings, both unreachable from the corpus and the property
/// suite, both reported rather than papered over:
///
/// * Python `int` is unbounded; this carries `i64`. An `int` outside
///   `i64` fails extraction, and an `int` op that overflows raises
///   `OverflowError` where CPython would widen to a bignum.
/// * `bool` is an `int` subclass in Python, so it extracts as
///   `Int(0 | 1)`; CPython would return the `bool` itself and `sig()`
///   would render `('bool', True)`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum PyNum {
    Int(i64),
    Float(f64),
}

impl PyNum {
    pub fn as_f64(self) -> f64 {
        match self {
            PyNum::Int(i) => i as f64,
            PyNum::Float(f) => f,
        }
    }

    /// `math.isfinite(x)` — always true for an `int`.
    pub fn is_finite(self) -> bool {
        match self {
            PyNum::Int(_) => true,
            PyNum::Float(f) => f.is_finite(),
        }
    }

    pub fn py_add(self, other: PyNum) -> DfmResult<PyNum> {
        match (self, other) {
            (PyNum::Int(a), PyNum::Int(b)) => {
                a.checked_add(b).map(PyNum::Int).ok_or(DfmError::IntOverflow)
            }
            _ => Ok(PyNum::Float(self.as_f64() + other.as_f64())),
        }
    }

    pub fn py_sub(self, other: PyNum) -> DfmResult<PyNum> {
        match (self, other) {
            (PyNum::Int(a), PyNum::Int(b)) => {
                a.checked_sub(b).map(PyNum::Int).ok_or(DfmError::IntOverflow)
            }
            _ => Ok(PyNum::Float(self.as_f64() - other.as_f64())),
        }
    }

    pub fn py_mul(self, other: PyNum) -> DfmResult<PyNum> {
        match (self, other) {
            (PyNum::Int(a), PyNum::Int(b)) => {
                a.checked_mul(b).map(PyNum::Int).ok_or(DfmError::IntOverflow)
            }
            _ => Ok(PyNum::Float(self.as_f64() * other.as_f64())),
        }
    }

    /// Python's `<`. CPython compares `int` against `float` **exactly**
    /// (it does not widen the int to a double), so this does too.
    pub fn lt(self, other: PyNum) -> bool {
        match (self, other) {
            (PyNum::Int(a), PyNum::Int(b)) => a < b,
            (PyNum::Float(a), PyNum::Float(b)) => a < b,
            (PyNum::Int(a), PyNum::Float(b)) => int_lt_float(a, b),
            (PyNum::Float(a), PyNum::Int(b)) => float_lt_int(a, b),
        }
    }

    pub fn gt(self, other: PyNum) -> bool {
        other.lt(self)
    }
}

const I64_LIMIT_AS_F64: f64 = 9.223_372_036_854_776e18;

fn int_lt_float(a: i64, b: f64) -> bool {
    if b.is_nan() {
        return false;
    }
    let fl = b.floor();
    if fl >= I64_LIMIT_AS_F64 {
        return true;
    }
    if fl < -I64_LIMIT_AS_F64 {
        return false;
    }
    let fi = fl as i64;
    if a != fi {
        return a < fi;
    }
    // a == floor(b): a < b exactly when b carries a fractional part.
    b > fl
}

fn float_lt_int(a: f64, b: i64) -> bool {
    if a.is_nan() {
        return false;
    }
    let ce = a.ceil();
    if ce >= I64_LIMIT_AS_F64 {
        return false;
    }
    if ce < -I64_LIMIT_AS_F64 {
        return true;
    }
    let ci = ce as i64;
    if ci != b {
        return ci < b;
    }
    // ceil(a) == b: a < b exactly when a carries a fractional part.
    a < ce
}

/// CPython's builtin `max(a, b)` over the numeric tower — `b if b > a else
/// a`, so the **first** argument wins ties and NaN. Crucially it returns
/// *one of its arguments*, preserving that argument's Python type.
pub fn py_max_num(a: PyNum, b: PyNum) -> PyNum {
    if b.gt(a) { b } else { a }
}

/// CPython's builtin `min(a, b)` over the numeric tower; see [`py_max_num`].
pub fn py_min_num(a: PyNum, b: PyNum) -> PyNum {
    if b.lt(a) { b } else { a }
}

// ---------------------------------------------------------------------------
// Shared layer constants (pinned by `test_oracle_constants_match_production`)
// ---------------------------------------------------------------------------

/// `copper_balance._LAYER_ORDER_NAMES` — the canonical 4-layer stackup,
/// top to bottom, as it evaluates from `core.board.STANDARD_LAYER_ORDER`.
const LAYER_ORDER_NAMES: [&str; 4] = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"];

/// `annular_ring_check._EXTERNAL_LAYERS`.
const EXTERNAL_LAYERS: [&str; 2] = ["F.Cu", "B.Cu"];

// ===========================================================================
// thermal_relief
// ===========================================================================

/// `thermal_relief._POWER_NET_PATTERN`, compiled once.
///
/// Byte-identical alternation and flag to the shipped
/// `re.compile(..., re.IGNORECASE)`. Only `is_match` is used, so the two
/// engines' differing *alternation preference* (CPython backtracks
/// leftmost-first, `regex` is an automaton) cannot matter — the existence
/// of a match is engine-independent. `\b` and `(?i)` are Unicode-aware in
/// both.
fn power_net_pattern() -> &'static regex::Regex {
    static RE: OnceLock<regex::Regex> = OnceLock::new();
    RE.get_or_init(|| {
        #[expect(
            clippy::unwrap_used,
            reason = "compile-time-constant pattern; `power_net_pattern_compiles` proves it parses"
        )]
        regex::Regex::new(concat!(
            r"(?i)\b(?:",
            r"GND|PGND|AGND|DGND|CGND|",
            r"[A-Z]*GND|",
            r"VCC|VDD|VEE|VPP|VBB|VREF|VBAT|",
            r"VDDIO|AVDD|DVDD|VCCINT|VCCO|VDD_CORE|",
            r"POWER|PVCC|PVDD",
            r")\b",
        ))
        .unwrap()
    })
}

/// `thermal_relief._is_power_net` — `bool(_POWER_NET_PATTERN.search(name))`.
pub fn is_power_net(net_name: &str) -> bool {
    power_net_pattern().is_match(net_name)
}

/// `thermal_relief._connects_to_power_plane`.
///
/// The via's two layers are passed as scalars: the kernel reads nothing
/// else off it. `plane_nets` arrives as a sequence because a `frozenset`'s
/// *iteration order* is not part of the contract (defect D1) while its
/// membership is — and membership is all this kernel uses.
pub fn connects_to_power_plane(
    net_name: &str,
    from_layer: &str,
    to_layer: &str,
    plane_layers: &[String],
    plane_nets: &[String],
) -> bool {
    // Net-class verification: must be a declared plane net.
    if !plane_nets.iter().any(|n| n == net_name) {
        return false;
    }
    // Layer check: the via must touch at least one plane layer.
    plane_layers.iter().any(|l| l == from_layer) || plane_layers.iter().any(|l| l == to_layer)
}

/// `thermal_relief._generate_spoke_segments`, with `board = None` (the
/// clamping arm is [`clamp_to_rect_outline`], called by the shim).
///
/// `pad_radius` is `math.hypot` (B4). `spoke_length` is the builtin `max`,
/// so a NaN `clearance_gap * 2.0` wins over the `spoke_width` arm (B5).
/// `angle` keeps the shipped left-to-right chain (B7).
pub fn generate_spoke_segments(
    cx: f64,
    cy: f64,
    pad_w: f64,
    pad_h: f64,
    spoke_count: i64,
    spoke_width: f64,
    clearance_gap: f64,
) -> Vec<((f64, f64), (f64, f64))> {
    let pad_radius = pymath::py_hypot(pad_w / 2.0, pad_h / 2.0);
    let spoke_length = pymath::py_max(clearance_gap * 2.0, spoke_width * 2.0);

    let mut segments = Vec::new();
    for i in 0..spoke_count.max(0) {
        // `2.0 * math.pi * i / spoke_count` — the divide stays last.
        let angle = 2.0 * std::f64::consts::PI * (i as f64) / (spoke_count as f64);
        let dx = pymath::cos(angle);
        let dy = pymath::sin(angle);

        // Start point — just outside the pad + clearance.
        let start_r = pad_radius + clearance_gap;
        let x1 = cx + start_r * dx;
        let y1 = cy + start_r * dy;

        // End point — start + spoke length.
        let x2 = cx + (start_r + spoke_length) * dx;
        let y2 = cy + (start_r + spoke_length) * dy;

        segments.push(((x1, y1), (x2, y2)));
    }
    segments
}

/// `thermal_relief._clamp_to_board_outline`, **rectangular arm only**.
///
/// The clamp is `max(x_min, min(x, x_max))`, CPython min-then-max: a NaN
/// `x` clamps to `x_min` — the board's left edge — rather than staying NaN
/// or going to `x_max` (B5). `f64::clamp` would panic here, and
/// `np.clip` would return `x_max`. The two `isfinite` guards return the
/// point unchanged, so an infinite board dimension is a pass-through, not
/// a clamp to infinity.
pub fn clamp_to_rect_outline(
    x: PyNum,
    y: PyNum,
    origin_x: PyNum,
    origin_y: PyNum,
    width: PyNum,
    height: PyNum,
) -> DfmResult<(PyNum, PyNum)> {
    if !(width.is_finite() && height.is_finite()) {
        return Ok((x, y));
    }
    if !(origin_x.is_finite() && origin_y.is_finite()) {
        return Ok((x, y));
    }
    let (x_min, y_min) = (origin_x, origin_y);
    let (x_max, y_max) = (origin_x.py_add(width)?, origin_y.py_add(height)?);
    Ok((
        py_max_num(x_min, py_min_num(x, x_max)),
        py_max_num(y_min, py_min_num(y, y_max)),
    ))
}

// ===========================================================================
// acid_trap_detection
// ===========================================================================

/// `acid_trap_detection._calculate_angle` — the angle at `p2` in degrees.
///
/// Four traps live in these fifteen lines:
/// `sqrt(x ** 2 + y ** 2)` is neither `hypot` nor `x * x`;
/// `max(-1.0, min(1.0, cos))` sends a NaN cosine to `+1.0` (so the kernel
/// returns `acos(1.0) == 0.0`, **not** the `180.0` degenerate fallback —
/// the other nesting gives `-1.0` and `180.0`);
/// `math.degrees` is one multiply by `180.0 / pi`; and `round(deg, 9)` is
/// decimal, and flips the 60-degree severity boundary.
///
/// # Errors
///
/// [`DfmError::PowOverflow`] when an arm's `x ** 2` overflows to infinity.
/// CPython's `float.__pow__` **raises** `OverflowError` there rather than
/// returning `inf`, so a port that used `x * x` — or even `pow` without
/// the errno check — would silently return an angle where the reference
/// raises. Three corpus rows reach it.
pub fn calculate_angle(
    p1x: f64,
    p1y: f64,
    p2x: f64,
    p2y: f64,
    p3x: f64,
    p3y: f64,
) -> DfmResult<f64> {
    // Vectors from p2 to p1 and p3.
    let v1 = (p1x - p2x, p1y - p2y);
    let v2 = (p3x - p2x, p3y - p2y);

    // Dot product and magnitudes.
    let sq = |v: f64| pymath::py_pow(v, 2.0).map_err(|_| DfmError::PowOverflow);
    let dot = v1.0 * v2.0 + v1.1 * v2.1;
    let mag1 = (sq(v1.0)? + sq(v1.1)?).sqrt();
    let mag2 = (sq(v2.0)? + sq(v2.1)?).sqrt();

    if mag1 == 0.0 || mag2 == 0.0 {
        return Ok(180.0); // Degenerate case
    }

    let cos_angle = dot / (mag1 * mag2);
    let cos_angle = pymath::py_max(-1.0, pymath::py_min(1.0, cos_angle)); // Clamp to [-1, 1]

    let angle_rad = pymath::acos(cos_angle);

    // Floating-point edge case: acos may still produce NaN.
    if angle_rad.is_nan() {
        return Ok(180.0);
    }

    // Round to eliminate floating-point noise.
    Ok(pymath::py_round(pymath::degrees(angle_rad), 9))
}

/// `acid_trap_detection._classify_severity`.
///
/// A NaN angle falls through both `<` tests to `"low"`; a non-finite or
/// negative width returns the base band with no demotion; `-0.0 < 0` is
/// false, so a negative-zero width *does* demote.
pub fn classify_severity(angle: f64, trace_width_mm: f64) -> &'static str {
    let base = if angle < 45.0 {
        "high" // Very acute - critical
    } else if angle < 60.0 {
        "medium" // Moderate concern
    } else {
        "low" // Minor issue
    };

    if !trace_width_mm.is_finite() || trace_width_mm < 0.0 {
        return base;
    }

    if trace_width_mm < 0.2 {
        return match base {
            "high" => "medium",
            "medium" => "low",
            other => other, // "low" stays "low"
        };
    }

    base
}

// ===========================================================================
// power_plane
// ===========================================================================

/// `power_plane._board_bounds` — `(ox, oy, ox + width, oy + height)`.
pub fn board_bounds(
    origin_x: PyNum,
    origin_y: PyNum,
    width: PyNum,
    height: PyNum,
) -> DfmResult<(PyNum, PyNum, PyNum, PyNum)> {
    Ok((
        origin_x,
        origin_y,
        origin_x.py_add(width)?,
        origin_y.py_add(height)?,
    ))
}

/// `power_plane._rect_polygon` — the 4 corners of an AABB, CCW.
///
/// A pure permutation of its inputs: no arithmetic, so each corner keeps
/// the Python type it arrived with.
pub fn rect_polygon(
    x_min: PyNum,
    y_min: PyNum,
    x_max: PyNum,
    y_max: PyNum,
) -> [(PyNum, PyNum); 4] {
    [
        (x_min, y_min),
        (x_max, y_min),
        (x_max, y_max),
        (x_min, y_max),
    ]
}

/// `power_plane.generate_power_pours`, reduced to the bounds it computes.
///
/// The domain names, the layer and the polygon are threaded by the
/// delegation shim (`_rect_polygon` of each bounds tuple); this kernel is
/// the strip partition.
///
/// `strip_x_min = x_min + i * (strip_width + isolation_gap_mm)` keeps the
/// addition **inside** the multiply (B7): distributing it changes the
/// result, and the last strip's `x_max` therefore does *not* generally
/// equal the board's `x_max` — measured on 34.15% of random
/// configurations, which is why "the pours tile the board" is not
/// asserted as a bit-exact invariant anywhere.
///
/// `n_domains == 0` returns `[]` **before** the gap check, matching the
/// shipped `if not resolved: return []` ordering.
pub fn power_pour_bounds(
    x_min: PyNum,
    y_min: PyNum,
    x_max: PyNum,
    y_max: PyNum,
    n_domains: usize,
    isolation_gap_mm: PyNum,
) -> DfmResult<Vec<(f64, PyNum, f64, PyNum)>> {
    if n_domains == 0 {
        return Ok(Vec::new());
    }
    if isolation_gap_mm.lt(PyNum::Int(0)) {
        return Err(DfmError::NegativeIsolationGap { gap: isolation_gap_mm });
    }

    let n = n_domains;
    let total_width = x_max.py_sub(x_min)?;
    let total_gap = isolation_gap_mm.py_mul(PyNum::Int(n as i64 - 1))?;
    // Python's `/` on ints yields a float, so `strip_width` is always a float.
    let strip_width = total_width.py_sub(total_gap)?.as_f64() / (n as f64);
    if strip_width <= 0.0 {
        return Err(DfmError::BoardTooNarrow { total_width, n, gap: isolation_gap_mm });
    }

    let mut pours = Vec::with_capacity(n);
    for i in 0..n {
        let strip_x_min =
            x_min.as_f64() + (i as f64) * (strip_width + isolation_gap_mm.as_f64());
        let strip_x_max = strip_x_min + strip_width;
        pours.push((strip_x_min, y_min, strip_x_max, y_max));
    }
    Ok(pours)
}

/// `power_plane._thermal_via_positions` — an NxN grid of via centres.
///
/// `side = int(round(count ** 0.5))` is libm `pow` then round-half-even
/// (B3 + B7): `c ** 0.5` differs from `math.sqrt(c)` for 137 integers in
/// `1..100000`, so getting this wrong misclassifies a perfect square.
///
/// A negative `count` reproduces CPython's chain exactly: `(-1) ** 0.5` is
/// a **complex**, and `round(complex)` raises `TypeError`. That is a
/// pinned corpus row, not a hypothetical.
pub fn thermal_via_positions(
    cx: f64,
    cy: f64,
    count: i64,
    pitch_mm: f64,
) -> DfmResult<Vec<(f64, f64)>> {
    if count < 0 {
        return Err(DfmError::ComplexRound);
    }
    let side = pymath::py_round_to_int(pymath::pow(count as f64, 0.5)) as i64;
    if side.checked_mul(side) != Some(count) {
        return Err(DfmError::NotAPerfectSquare { count });
    }

    let span = ((side - 1) as f64) * pitch_mm;
    let x0 = cx - span / 2.0;
    let y0 = cy - span / 2.0;

    let mut out = Vec::with_capacity(count.clamp(0, 1 << 16) as usize);
    for row in 0..side {
        for col in 0..side {
            out.push((x0 + (col as f64) * pitch_mm, y0 + (row as f64) * pitch_mm));
        }
    }
    Ok(out)
}

// ===========================================================================
// copper_balance
// ===========================================================================

/// `copper_balance._via_annular_area` — `pi * (r_pad^2 - r_hole^2)`.
///
/// Here the squares really are `r * r`, **not** `** 2`: it is a different
/// expression from [`calculate_angle`]'s and the two are not unified.
/// `getattr(via, "drill", 0.0) or 0.0` is reproduced by the `-0.0 -> 0.0`
/// normalisation: `-0.0` is falsy in Python, so it takes the no-hole path.
pub fn via_annular_area(diameter: f64, drill: f64) -> f64 {
    // `drill or 0.0` — a falsy drill (0.0 or -0.0) becomes +0.0.
    let drill = if drill == 0.0 { 0.0 } else { drill };

    // Guard: NaN / inf diameter or drill -> 0.0
    if diameter.is_nan() || drill.is_nan() || diameter.is_infinite() || drill.is_infinite() {
        return 0.0;
    }
    // Guard: non-positive diameter or drill >= diameter -> 0.0
    if diameter <= 0.0 || drill >= diameter {
        return 0.0;
    }

    let r_pad = diameter / 2.0;
    let r_hole = if drill > 0.0 { drill / 2.0 } else { 0.0 };
    std::f64::consts::PI * (r_pad * r_pad - r_hole * r_hole)
}

/// `copper_balance._layer_is_between` — strict betweenness in the 4-layer
/// stackup. An unknown layer name is the shipped `ValueError` -> `False`.
pub fn layer_is_between(from_layer: &str, to_layer: &str, candidate: &str) -> bool {
    let index = |name: &str| LAYER_ORDER_NAMES.iter().position(|l| *l == name);
    let (Some(idx_from), Some(idx_to), Some(idx_candidate)) =
        (index(from_layer), index(to_layer), index(candidate))
    else {
        return false;
    };
    let lo = idx_from.min(idx_to);
    let hi = idx_from.max(idx_to);
    lo < idx_candidate && idx_candidate < hi
}

/// `copper_balance._calculate_layer_copper_area`'s RoutePath3D branch.
///
/// The layer label comes from `segments[i]`, so the **last** vertex's
/// layer never counts. `math.hypot` (B4) and the left-to-right `+=`
/// accumulation order are both part of the contract: summing in any other
/// order (pairwise, Neumaier-compensated, or reversed) changes the last
/// bits.
///
/// `layers` is `&[&str]` rather than `&[String]` so the pyo3 boundary can
/// borrow the Python strings instead of allocating one `String` per
/// vertex: measured, that allocation alone made this kernel **1.42x
/// slower than the Python it replaces** on the shared corpus, whose runs
/// are 2-65 vertices long.
pub fn segment_run_copper_area(
    xs: &[f64],
    ys: &[f64],
    layers: &[&str],
    layer_name: &str,
    width_mm: f64,
) -> DfmResult<f64> {
    if xs.len() != ys.len() || xs.len() != layers.len() {
        return Err(DfmError::RaggedInput(
            "xs, ys and layers must be the same length (they are one list of \
             (x, y, layer) triples on the Python side)",
        ));
    }
    let mut copper_area = 0.0f64;
    for i in 0..layers.len().saturating_sub(1) {
        if layers[i] == layer_name {
            let seg_length = pymath::py_hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]);
            copper_area += seg_length * width_mm;
        }
    }
    Ok(copper_area)
}

// ===========================================================================
// via_placement
// ===========================================================================

/// `via_placement._place_vias_for_path`'s segment-match scan.
///
/// First match wins, `abs(...) < 1e-4` on **both** axes, and a NaN on
/// either side never matches (`abs(nan) < 1e-4` is false).
pub fn via_segment_index(
    vx: f64,
    vy: f64,
    seg_xs: &[f64],
    seg_ys: &[f64],
) -> DfmResult<Option<usize>> {
    if seg_xs.len() != seg_ys.len() {
        return Err(DfmError::RaggedInput(
            "seg_xs and seg_ys must be the same length",
        ));
    }
    for i in 0..seg_xs.len() {
        if (seg_xs[i] - vx).abs() < 1e-4 && (seg_ys[i] - vy).abs() < 1e-4 {
            return Ok(Some(i));
        }
    }
    Ok(None)
}

/// `via_placement._get_adjacent_layer` — the shipped `dict.get`, including
/// `B.Cu -> In2.Cu` (the map is not a cycle) and `None` for anything else.
pub fn adjacent_layer(layer_name: &str) -> Option<&'static str> {
    match layer_name {
        "F.Cu" => Some("In1.Cu"),
        "In1.Cu" => Some("In2.Cu"),
        "In2.Cu" => Some("B.Cu"),
        "B.Cu" => Some("In2.Cu"),
        _ => None,
    }
}

// ===========================================================================
// annular_ring_check
// ===========================================================================

/// `annular_ring_check._check_via`, reduced to the three numbers a
/// violation carries: `(actual_ring_width, minimum_required, deficiency)`.
///
/// The shim keeps the `AnnularRingViolation` construction, so
/// `net_name` / `via_position` / `pad_diameter` / `drill_diameter` are
/// threaded through Python-side untouched (signed zeros and NaN included);
/// `deficiency` is a derived property, recomputed here in the same order
/// (`minimum_required - actual_ring_width`).
///
/// Infinities are deliberately **not** guarded, matching the shipped
/// kernel: an infinite drill gives `ring_width == -inf` and therefore a
/// violation, while an infinite diameter gives `+inf` and none.
pub fn check_annular_ring(
    diameter: f64,
    drill: f64,
    from_layer: &str,
    to_layer: &str,
    via_type: Option<&str>,
    min_annular_ring: f64,
    microvia_ring_mm: f64,
) -> Option<(f64, f64, f64)> {
    // Guard: NaN / zero / negative drill produces invalid ring widths.
    if drill.is_nan() || diameter.is_nan() || drill <= 0.0 {
        return None;
    }

    // Ring width = (pad_diameter - drill_diameter) / 2
    let ring_width = (diameter - drill) / 2.0;

    // IPC-6012: external layers use the full min_annular_ring; internal
    // layers use half that value.
    let is_external = |l: &str| EXTERNAL_LAYERS.contains(&l);
    let mut threshold = if is_external(from_layer) || is_external(to_layer) {
        min_annular_ring
    } else {
        min_annular_ring * 0.5
    };

    // Via-type override: microvias use the IPC-6016 threshold.
    if via_type == Some("microvia") {
        threshold = microvia_ring_mm;
    }

    // Guard: a NaN threshold produces meaningless comparisons.
    if threshold.is_nan() {
        return None;
    }

    const FP_EPSILON: f64 = 1e-12;
    if ring_width <= threshold + FP_EPSILON {
        Some((ring_width, threshold, threshold - ring_width))
    } else {
        None
    }
}

// ===========================================================================
// teardrop_generation
// ===========================================================================

/// A teardrop's numeric payload: `(connection_point, length_mm, width_mm)`.
/// The layer is the caller's `path_layer`, threaded back unchanged.
pub type TeardropDims = ((f64, f64), f64, f64);

/// `teardrop_generation._generate_via_teardrop`.
///
/// The `nearest_idx` argmin is CPython's `min(range(n), key=...)`, which
/// keeps the **first** minimum on an exact tie and never lets a NaN key
/// displace the incumbent — a via exactly between two coordinates picks
/// the earlier one, which selects a different neighbour and therefore a
/// different direction vector. `math.hypot` (B4) is both the key and the
/// magnitude.
///
/// The `warnings.warn` on a bad diameter stays in the shim: the warning is
/// not the contract, the `None` is.
#[expect(
    clippy::too_many_arguments,
    reason = "the flattened call shape is fixed by test_dfm_rust_differential.py"
)]
pub fn via_teardrop(
    via_x: f64,
    via_y: f64,
    diameter: f64,
    from_layer: &str,
    to_layer: &str,
    path_layer: Option<&str>,
    coord_xs: &[f64],
    coord_ys: &[f64],
    width_mm: f64,
    length_ratio: f64,
) -> DfmResult<Option<TeardropDims>> {
    if coord_xs.len() != coord_ys.len() {
        return Err(DfmError::RaggedInput(
            "coord_xs and coord_ys must be the same length",
        ));
    }
    // Guard: skip vias with NaN, infinite, or non-positive diameter.
    if diameter.is_nan() || !diameter.is_finite() || diameter <= 0.0 {
        return Ok(None);
    }

    // Guard: only generate a teardrop when the route's path is on a layer
    // this via touches.
    let Some(path_layer) = path_layer else {
        return Ok(None);
    };
    if path_layer != from_layer && path_layer != to_layer {
        return Ok(None);
    }

    let n = coord_xs.len();
    if n < 2 {
        return Ok(None); // no segment to infer direction from
    }

    // `min(range(n), key=...)` — strict `<`, so the first minimum wins and
    // a NaN key never displaces the incumbent.
    let key = |i: usize| pymath::py_hypot(coord_xs[i] - via_x, coord_ys[i] - via_y);
    let mut nearest_idx = 0usize;
    let mut best = key(0);
    for i in 1..n {
        let k = key(i);
        if k < best {
            best = k;
            nearest_idx = i;
        }
    }

    // Prefer the next coordinate; fall back to the previous one.
    let neighbour = if nearest_idx < n - 1 {
        nearest_idx + 1
    } else {
        nearest_idx - 1
    };

    let dx = coord_xs[neighbour] - via_x;
    let dy = coord_ys[neighbour] - via_y;
    let dist = pymath::py_hypot(dx, dy);
    if dist < 1e-9 {
        return Ok(None); // coincident points -- cannot determine direction
    }

    // Unit vector from the via centre toward the trace.
    let ux = dx / dist;
    let uy = dy / dist;

    // Connection point at the via annulus perimeter.
    let connection_point = (via_x + ux * diameter / 2.0, via_y + uy * diameter / 2.0);

    // Guard against NaN / +inf trace width; clamp -inf / negative to 0.
    if width_mm.is_nan() || width_mm == f64::INFINITY {
        return Ok(None);
    }
    let trace_width = pymath::py_max(0.0, width_mm);
    let teardrop_length = diameter * length_ratio;
    let teardrop_width = pymath::py_min(diameter * 0.6, trace_width * 2.0);

    // Only add a teardrop if the via is at least as large as the threshold.
    if diameter >= trace_width * 1.2 {
        return Ok(Some((connection_point, teardrop_length, teardrop_width)));
    }
    Ok(None)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests;
