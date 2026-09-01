//! Wave-4 Phase B: the `router_v6/net_ordering` kernel in Rust.
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_net_ordering_py_oracle.py` -- a
//! verbatim extraction of `router_v6/net_ordering.py` at
//! `15110feccc6ec9389f0777d3cff1ce9f81b11068`, which is **character-identical
//! to `origin/main` today** (verified: `git diff 15110feccc origin/main --
//! .../net_ordering.py` is empty).  Unlike this cluster's two sibling
//! oracles, no defect fix has landed under this one.
//!
//! Why this crate
//! --------------
//! `net_ordering`'s kernel is a total-order comparator over nets and loops,
//! not geometry.  `temper-rust-router` already owns that domain --
//! `types_py_bridge`/the core-crate types carry nets and `loop_extractor/`
//! carries loops -- and the differential's
//! adapter block names `temper_rust_router` as the migration target, so
//! hosting the kernel here means the differential binds with **zero edits to
//! the test file**.  `temper-geometry` (where cluster E points) is the wrong
//! home: there is no geometry here beyond `max(xs) - min(xs)`.
//!
//! Semantics that are NOT the obvious Rust ones
//! --------------------------------------------
//! * `max`/`min` are CPython's **iterable** builtins: a left-to-right scan
//!   keeping the incumbent unless strictly beaten.  `max([nan, 5.0])` is
//!   `nan`; `max([5.0, nan])` is `5.0`.  `f64::max` discards NaN and gets
//!   both wrong.  See [`py_max`] / [`py_min`].
//! * A quadrant rotation is **not** an exact axis swap.  `cos(pi/2)` is
//!   `0x1.1a62633145c07p-54`, not `0`, so `rotate_local_to_world` leaves a
//!   residue proportional to the other coordinate.  An "optimised" axis swap
//!   is more correct and fails the differential.  [`rotate_local_to_world`]
//!   keeps the multiply-add form.
//! * `rot * PI / 2.0` is `(rot * PI) / 2.0`.  Division by 2.0 is exact, so
//!   this agrees with `rot * FRAC_PI_2` -- measured on 0 of 20,000 random
//!   values does it diverge (recorded in the PR body as a non-divergence).
//!   The multiply-then-divide form is kept anyway because it is what the
//!   oracle writes.
//! * Python tuple comparison uses `PyObject_RichCompareBool`, which has an
//!   **identity shortcut**: `x is y` implies `x == y`, even for NaN.  The
//!   key comparator retains this distinction for any Python-originated key
//!   elements, while `order_nets` uses freshly computed values.
//! * `list.sort` is CPython's timsort.  With a NaN wirelength the 6-tuple
//!   key stops being a total order and the output becomes a function of the
//!   algorithm, not just of the data.  [`py_list_sort`] is a port of CPython
//!   3.12's `count_run` + `binarysort` + `merge_compute_minrun`, not a call
//!   to `sort_by`.

use std::collections::HashMap;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyDict;

// ===========================================================================
// CPython builtin `max` / `min` over an iterable  (catalog B5)
// ===========================================================================

/// CPython `max(iterable)` for floats: keep the incumbent unless `x > best`.
///
/// A NaN early in the sequence therefore poisons the result (nothing is
/// `>` it), while a NaN later in it is silently dropped.  This is neither
/// `f64::max` (which discards NaN) nor `np.maximum` (which propagates from
/// either side).
fn py_max(xs: &[f64]) -> f64 {
    let mut best = xs[0];
    for &x in &xs[1..] {
        if x > best {
            best = x;
        }
    }
    best
}

/// CPython `min(iterable)` for floats -- the `<` mirror of [`py_max`].
fn py_min(xs: &[f64]) -> f64 {
    let mut best = xs[0];
    for &x in &xs[1..] {
        if x < best {
            best = x;
        }
    }
    best
}

// ===========================================================================
// Geometry: pin_world_position  (core/pin_geometry.py + geometry/kicad_transform.py)
// ===========================================================================

/// `core/pin_geometry._normalize_rotation`'s **integer-index** branch:
/// a quarter-turn index becomes radians.
///
/// Out-of-range indices (`5`, `-1`) keep multiplying without validation,
/// because the oracle does.
fn normalize_rotation_index(index: i64) -> f64 {
    (index as f64) * std::f64::consts::PI / 2.0
}

/// `core/pin_geometry._normalize_rotation`, whole dispatch.
///
/// Mirrors `temper_geometry`'s `rot_to_radians`, the canonical implementation
/// the Python shim binds as `_normalize_rotation`:
///
/// ```text
/// None  -> 0.0
/// int   -> index * PI / 2      (a quarter-turn INDEX)
/// float -> as-is               (already RADIANS)
/// ```
///
/// The int and float branches mean different things, and that is the whole
/// subtlety. This kernel used to bind the value as `Option<i64>`, which the
/// migration-narrowing gate flagged: pyo3 REJECTS a non-integral float on an
/// `i64` extract rather than truncating, so a fractional rotation raised
/// `TypeError` where the Python arm returned an angle -- the same defect
/// already fixed in `escape_via.rs`.
///
/// Widening the binding to `Option<f64>` does NOT fix it. That accepts the
/// float but then multiplies it by PI/2, treating radians as an index; the
/// supplemental regression caught the resulting divergence
/// (`0x1.6a09e667f3bccp+0` vs `0x1.5b64e20408024p+0` at `rotation=0.5`).
/// Reproducing the dispatch is the fix; widening alone just trades a loud
/// `TypeError` for a quiet wrong number.
///
/// `bool` extracts as `i64` in pyo3 and so takes the index branch, matching
/// the oracle's `isinstance(rotation, int)` being True for `bool`.
///
/// Duplicated rather than imported: `temper-rust-router` does not depend on
/// `temper-geometry`, and adding that edge for one 8-line dispatch is a
/// heavier change than this comment. If the canonical version changes, this
/// must change with it.
#[cfg(feature = "python")]
fn rot_to_radians(rot: &Bound<'_, PyAny>) -> PyResult<f64> {
    if rot.is_none() {
        return Ok(0.0);
    }
    if let Ok(index) = rot.extract::<i64>() {
        return Ok(normalize_rotation_index(index));
    }
    rot.extract::<f64>()
}

/// `geometry/kicad_transform.rotate_local_to_world` -- R(-theta).
///
/// Deliberately NOT special-cased for quadrant angles: `cos(pi/2)` is
/// `6.123233995736766e-17`, and the residue it leaves is part of the pinned
/// contract.
fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let c = theta_rad.cos();
    let s = theta_rad.sin();
    (x * c + y * s, -x * s + y * c)
}

/// `core/pin_geometry.pin_world_position`.
///
/// `side` is not carried by the `net_ordering` corpus shape (its components
/// Rows may carry an optional 5th element, `initial_side`. Until 2026-08-06
/// they could not, and this function did not model the bottom-side X mirror
/// at all -- the comment here asserted that side was "0 for every component
/// this kernel can see", which was true of the corpus and false of any real
/// board with a back-side component.
fn pin_world_position(pin_pos: (f64, f64), comp: &CompRow) -> (f64, f64) {
    let rotation_rad = comp.rotation_rad;
    // `side = comp.initial_side or 0`, then mirror X BEFORE rotation --
    // KiCad's bottom-side convention, and the order matters: mirroring after
    // rotation gives a different point for any non-zero rotation.
    let side = comp.side.unwrap_or(0);
    let (mut px, py) = pin_pos;
    if side == 1 {
        px = -px;
    }
    let (rx, ry) = rotate_local_to_world(px, py, rotation_rad);
    let cpos = comp.position.unwrap_or((0.0, 0.0));
    (cpos.0 + rx, cpos.1 + ry)
}

// ===========================================================================
// Corpus row shapes
// ===========================================================================

struct PinRow {
    position: (f64, f64),
    net: Option<String>,
}

struct CompRow {
    position: Option<(f64, f64)>,
    /// `_normalize_rotation(initial_rotation_quadrant)` -- RESOLVED RADIANS, not the
    /// raw index. Resolution happens at parse time (`rot_to_radians`) because
    /// the int/float dispatch needs the live Python object, which is gone by
    /// the time this struct exists.
    rotation_rad: f64,
    /// `Component.initial_side`. Optional so a 4-tuple row still parses.
    side: Option<i64>,
    pins: Vec<PinRow>,
}

/// `[(ref, initial_position, rotation, [(pin_number, (px, py), net)])]`.
#[cfg(feature = "python")]
fn parse_components(components: &Bound<'_, PyAny>) -> PyResult<Vec<CompRow>> {
    let mut out = Vec::new();
    for row in components.try_iter()? {
        let row = row?;
        let position: Option<(f64, f64)> = row.get_item(1)?.extract()?;
        let rotation_rad = rot_to_radians(&row.get_item(2)?)?;
        // 5th element is optional: a 4-tuple row keeps the old shape and is
        // treated as front-side, which is what every pre-existing corpus row
        // relies on.
        let side: Option<i64> = match row.get_item(4) {
            Ok(v) => v.extract().ok(),
            Err(_) => None,
        };
        let mut pins = Vec::new();
        for p in row.get_item(3)?.try_iter()? {
            let p = p?;
            pins.push(PinRow {
                position: p.get_item(1)?.extract()?,
                net: p.get_item(2)?.extract()?,
            });
        }
        out.push(CompRow {
            position,
            rotation_rad,
            side,
            pins,
        });
    }
    Ok(out)
}

/// Every pin on `net_name`, in component-then-pin iteration order.
///
/// The order is load-bearing: `py_max`/`py_min` are position-dependent under
/// NaN, so this list may not be sorted or reordered.
fn pin_positions_for_net(net_name: &str, components: &[CompRow]) -> Vec<(f64, f64)> {
    let mut out = Vec::new();
    for comp in components {
        for pin in &comp.pins {
            if pin.net.as_deref() == Some(net_name) {
                out.push(pin_world_position(pin.position, comp));
            }
        }
    }
    out
}

/// The bounding box `(width, height)` shared by `compute_hpwl` and
/// `compute_bbox_area`.  The two differ by exactly one operator downstream --
/// `w + h` vs `w * h` -- and nothing else, which is why the box is computed
/// once here rather than either being derived from the other.
fn bbox_span(net_name: &str, components: &[CompRow]) -> Option<(f64, f64)> {
    let positions = pin_positions_for_net(net_name, components);
    if positions.len() < 2 {
        return None;
    }
    let xs: Vec<f64> = positions.iter().map(|p| p.0).collect();
    let ys: Vec<f64> = positions.iter().map(|p| p.1).collect();
    Some((py_max(&xs) - py_min(&xs), py_max(&ys) - py_min(&ys)))
}

fn compute_hpwl(net_name: &str, components: &[CompRow]) -> f64 {
    match bbox_span(net_name, components) {
        None => 0.0,
        Some((w, h)) => w + h,
    }
}

fn compute_bbox_area(net_name: &str, components: &[CompRow]) -> f64 {
    match bbox_span(net_name, components) {
        None => 0.0,
        Some((w, h)) => w * h,
    }
}

// ===========================================================================
// get_net_class_from_string  --  an EXACT-match dict, 22 keys
// ===========================================================================

/// Mirror of the oracle's `mapping.get(net_class_str, NetClass.SIGNAL)`.
///
/// Exact match only.  Not `eq_ignore_ascii_case`, not `starts_with`, not
/// trimmed: `"HIGHVOLTAGE"`, `" GND"`, `"POWER"` and `"Signal\n"` all fall
/// through to `SIGNAL`.
fn net_class_from_string(s: &str) -> i64 {
    match s {
        "HighVoltage" | "highvoltage" | "HV" => 0,
        "Differential" | "differential" | "DiffPair" => 1,
        "Power" | "power" => 2,
        "GateDrive" | "gatedrive" | "Gate" | "GateDriveHV" | "gatedrivehv" | "GateDriveSELV"
        | "gatedriveselv" => 3,
        "Signal" | "signal" | "FinePitch" | "finepitch" => 4,
        "Ground" | "ground" | "GND" => 5,
        _ => 4,
    }
}

// ===========================================================================
// get_loop_criticality
// ===========================================================================

struct LoopRow {
    name: String,
    criticality: i64,
    nets: Vec<String>,
}

fn priority_to_criticality(priority: &str) -> i64 {
    match priority {
        "CRITICAL" => 0,
        "HIGH" => 1,
        "MEDIUM" => 2,
        _ => 3,
    }
}

/// `[(loop_name, priority_name, [net, ...])]` -> loops, reproducing
/// `LoopCollection.add_loop`'s duplicate-name rejection.
///
/// `add_loop` raises `ValueError: Loop with name 'A' already exists`
/// (`temper-design-bundle/src/loops.rs`), and the corpus's `dup_loop` row
/// exercises it -- the differential captures the exception and compares it as
/// a value, so the message text is part of the contract.
#[cfg(feature = "python")]
fn parse_loops(loop_specs: &Bound<'_, PyAny>) -> PyResult<Vec<LoopRow>> {
    let mut out: Vec<LoopRow> = Vec::new();
    for row in loop_specs.try_iter()? {
        let row = row?;
        let name: String = row.get_item(0)?.extract()?;
        let priority: String = row.get_item(1)?.extract()?;
        let nets: Vec<String> = row.get_item(2)?.extract()?;
        if out.iter().any(|l| l.name == name) {
            return Err(PyValueError::new_err(format!(
                "Loop with name '{name}' already exists"
            )));
        }
        out.push(LoopRow {
            name,
            criticality: priority_to_criticality(&priority),
            nets,
        });
    }
    Ok(out)
}

/// The oracle's `min(best_criticality, criticality)` fold from 3, in
/// `LoopCollection` insertion order.  Net matching is exact, not a substring
/// test (`"N1"` must not match a loop carrying `"N10"`).
fn loop_criticality(net_name: &str, loops: &[LoopRow]) -> i64 {
    let containing: Vec<&LoopRow> = loops
        .iter()
        .filter(|l| l.nets.iter().any(|n| n == net_name))
        .collect();
    if containing.is_empty() {
        return 3;
    }
    let mut best = 3;
    for l in containing {
        best = best.min(l.criticality);
    }
    best
}

// ===========================================================================
// Net-order key and its comparison
// ===========================================================================

/// One element of the comparison key, carrying enough to reproduce CPython's
/// value comparison and its identity shortcut.
#[derive(Clone)]
enum KeyElem {
    Int(i64),
    /// A `float`, plus the identity of the Python object it came from, when
    /// there is one -- see [`py_eq_elem`].  `None` means "computed in Rust,
    /// no Python object behind it", and two `None`s are **not** identical:
    /// using a shared sentinel id here made every computed HPWL compare
    /// equal to every other, which silently collapsed `order_nets` to a
    /// name-only sort.
    Float(f64, Option<usize>),
    Str(String),
}

/// `PyObject_RichCompareBool(a, b, Py_EQ)` for a key element.
///
/// CPython short-circuits on identity **before** calling `==`, so two
/// references to the *same* NaN object compare equal. The comparator retains
/// that distinction for Python-originated values; `order_nets` supplies
/// freshly computed values instead.
fn py_eq_elem(a: &KeyElem, b: &KeyElem) -> bool {
    match (a, b) {
        (KeyElem::Int(x), KeyElem::Int(y)) => x == y,
        (KeyElem::Float(x, ida), KeyElem::Float(y, idb)) => {
            matches!((ida, idb), (Some(a), Some(b)) if a == b) || x == y
        }
        (KeyElem::Str(x), KeyElem::Str(y)) => x == y,
        _ => false,
    }
}

fn py_lt_elem(a: &KeyElem, b: &KeyElem) -> bool {
    match (a, b) {
        (KeyElem::Int(x), KeyElem::Int(y)) => x < y,
        (KeyElem::Float(x, _), KeyElem::Float(y, _)) => x < y,
        // Python compares `str` byte-wise by code point; Rust's `Ord` for
        // `str` is byte-wise over UTF-8, which is the same order.
        (KeyElem::Str(x), KeyElem::Str(y)) => x < y,
        _ => false,
    }
}

/// `tuple.__lt__`: find the first index that is not equal, and answer there.
/// Two fully-equal tuples are not less than one another.
fn py_key_lt(a: &[KeyElem], b: &[KeyElem]) -> bool {
    for (x, y) in a.iter().zip(b.iter()) {
        if py_eq_elem(x, y) {
            continue;
        }
        return py_lt_elem(x, y);
    }
    false
}

// ===========================================================================
// CPython's list.sort  (Objects/listobject.c)
// ===========================================================================
//
// `order_nets` calls `priorities.sort(key=...)`.  When every HPWL is finite
// and net names are distinct the key is a total order, and *any* stable sort
// agrees with CPython.  It stops being a total order the moment a pin
// coordinate is NaN -- the corpus's `nan_wirelength` row -- and then the
// answer is a property of the algorithm.  Measured on that row: 4 distinct
// orderings across the 6 permutations of 3 nets.  So the algorithm is ported,
// not approximated.

/// CPython `merge_compute_minrun`.
fn merge_compute_minrun(mut n: usize) -> usize {
    let mut r = 0usize;
    while n >= 64 {
        r |= n & 1;
        n >>= 1;
    }
    n + r
}

/// CPython `count_run`: the length of the initial ascending run, or of the
/// initial *strictly* descending run, which is then reversed in place.
/// Reversing only strictly-descending runs is what keeps the sort stable.
fn count_run<T>(a: &mut [T], lt: &dyn Fn(&T, &T) -> bool) -> usize {
    let hi = a.len();
    if hi <= 1 {
        return hi;
    }
    let mut n = 2usize;
    if lt(&a[1], &a[0]) {
        // descending
        while n < hi && lt(&a[n], &a[n - 1]) {
            n += 1;
        }
        a[..n].reverse();
    } else {
        while n < hi && !lt(&a[n], &a[n - 1]) {
            n += 1;
        }
    }
    n
}

/// CPython `binarysort`: binary insertion sort of `a[start..]` into the
/// already-sorted `a[..start]`.
///
/// The search is for the leftmost position `l` with `pivot < a[l]`, so an
/// element equal to the pivot keeps its earlier position -- stability.  With
/// an inconsistent comparator (NaN) the *path* of the binary search is what
/// determines the answer, which is why the midpoint rule `l + ((r - l) >> 1)`
/// is reproduced exactly rather than replaced with an equivalent-looking one.
fn binarysort<T>(a: &mut [T], start: usize, lt: &dyn Fn(&T, &T) -> bool) {
    let hi = a.len();
    let mut start = if start == 0 { 1 } else { start };
    while start < hi {
        let mut l = 0usize;
        let mut r = start;
        while l < r {
            let p = l + ((r - l) >> 1);
            if lt(&a[start], &a[p]) {
                r = p;
            } else {
                l = p + 1;
            }
        }
        // Rotate a[l..=start] right by one: the pivot lands at l.
        a[l..=start].rotate_right(1);
        start += 1;
    }
}

/// `memmove` within one slice for a `Clone` (not `Copy`) element type.
///
/// `slice::copy_within` requires `Copy`; the merge needs the same move for
/// `T: Clone`.  Only the descending-destination direction (`dst < src`) is
/// ever needed here, and a forward loop is correct for it.
fn clone_within<T: Clone>(a: &mut [T], src: usize, dst: usize, len: usize) {
    debug_assert!(dst <= src, "clone_within only supports dst <= src");
    for i in 0..len {
        a[dst + i] = a[src + i].clone();
    }
}

/// CPython's `MIN_GALLOP`.
const MIN_GALLOP: usize = 7;

/// One pending run in the merge stack: `[base, base+len)` plus its powersort
/// power.
#[derive(Clone, Copy)]
struct Run {
    base: usize,
    len: usize,
    power: u32,
}

/// The merge machinery, carrying the adaptive `min_gallop` that CPython
/// threads across every merge of a single sort.  It is *state*, not a
/// constant: leaving galloping mode penalises it and staying in rewards it,
/// so two merges of identical data can take different paths depending on
/// what came before.  Under an inconsistent comparator those paths reach
/// different answers, which is why it is modelled rather than fixed at 7.
struct MergeState<'a, T> {
    lt: &'a dyn Fn(&T, &T) -> bool,
    min_gallop: usize,
    pending: Vec<Run>,
    listlen: usize,
}

impl<'a, T: Clone> MergeState<'a, T> {
    fn new(lt: &'a dyn Fn(&T, &T) -> bool, listlen: usize) -> Self {
        Self {
            lt,
            min_gallop: MIN_GALLOP,
            pending: Vec::new(),
            listlen,
        }
    }

    /// CPython `gallop_left`: the leftmost index `i` in `[0, a.len()]` with
    /// `a[i-1] < key <= a[i]`.  Exponential search outward from `hint`, then
    /// a binary search over the bracket it leaves.
    fn gallop_left(&self, key: &T, a: &[T], hint: usize) -> usize {
        let n = a.len();
        let lt = self.lt;
        let mut lastofs = 0usize;
        let mut ofs = 1usize;
        if lt(&a[hint], key) {
            // a[hint] < key: gallop right until a[hint+ofs] >= key
            let maxofs = n - hint;
            while ofs < maxofs {
                if lt(&a[hint + ofs], key) {
                    lastofs = ofs;
                    ofs = (ofs << 1) + 1;
                } else {
                    break;
                }
            }
            if ofs > maxofs {
                ofs = maxofs;
            }
            lastofs += hint;
            ofs += hint;
        } else {
            // key <= a[hint]: gallop left until a[hint-ofs] < key
            let maxofs = hint + 1;
            while ofs < maxofs {
                if lt(&a[hint - ofs], key) {
                    break;
                }
                lastofs = ofs;
                ofs = (ofs << 1) + 1;
            }
            if ofs > maxofs {
                ofs = maxofs;
            }
            let k = lastofs;
            lastofs = hint - ofs;
            ofs = hint - k;
        }
        // Now a[lastofs] < key <= a[ofs]; binary search over (lastofs, ofs].
        lastofs += 1;
        while lastofs < ofs {
            let m = lastofs + ((ofs - lastofs) >> 1);
            if lt(&a[m], key) {
                lastofs = m + 1;
            } else {
                ofs = m;
            }
        }
        ofs
    }

    /// CPython `gallop_right`: the index `i` with `a[i-1] <= key < a[i]` --
    /// the `gallop_left` mirror with the comparison reversed, which is what
    /// puts equal elements on the other side and keeps the merge stable.
    fn gallop_right(&self, key: &T, a: &[T], hint: usize) -> usize {
        let n = a.len();
        let lt = self.lt;
        let mut lastofs = 0usize;
        let mut ofs = 1usize;
        if lt(key, &a[hint]) {
            // key < a[hint]: gallop left
            let maxofs = hint + 1;
            while ofs < maxofs {
                if lt(key, &a[hint - ofs]) {
                    lastofs = ofs;
                    ofs = (ofs << 1) + 1;
                } else {
                    break;
                }
            }
            if ofs > maxofs {
                ofs = maxofs;
            }
            let k = lastofs;
            lastofs = hint - ofs;
            ofs = hint - k;
        } else {
            // a[hint] <= key: gallop right
            let maxofs = n - hint;
            while ofs < maxofs {
                if lt(key, &a[hint + ofs]) {
                    break;
                }
                lastofs = ofs;
                ofs = (ofs << 1) + 1;
            }
            if ofs > maxofs {
                ofs = maxofs;
            }
            lastofs += hint;
            ofs += hint;
        }
        lastofs += 1;
        while lastofs < ofs {
            let m = lastofs + ((ofs - lastofs) >> 1);
            if lt(key, &a[m]) {
                ofs = m;
            } else {
                lastofs = m + 1;
            }
        }
        ofs
    }

    /// CPython `merge_lo`: `A` (the shorter, left run) is copied out and
    /// merged back left to right, preferring `A` on ties (`if b < a` takes
    /// `b`, otherwise `a`).
    fn merge_lo(&mut self, a: &mut [T], base_a: usize, na0: usize, nb0: usize) {
        let lt = self.lt;
        let temp: Vec<T> = a[base_a..base_a + na0].to_vec();
        let mut dest = base_a;
        let mut pa = 0usize; // index into temp
        let mut na = na0;
        let mut pb = base_a + na0; // index into a
        let mut nb = nb0;

        a[dest] = a[pb].clone();
        dest += 1;
        pb += 1;
        nb -= 1;
        if nb == 0 {
            a[dest..dest + na].clone_from_slice(&temp[pa..pa + na]);
            return;
        }
        if na == 1 {
            clone_within(a, pb, dest, nb);
            a[dest + nb] = temp[pa].clone();
            return;
        }

        let mut min_gallop = self.min_gallop;
        'outer: loop {
            let mut acount = 0usize;
            let mut bcount = 0usize;
            // One-at-a-time mode, until one run wins `min_gallop` in a row.
            loop {
                if lt(&a[pb], &temp[pa]) {
                    a[dest] = a[pb].clone();
                    dest += 1;
                    pb += 1;
                    bcount += 1;
                    acount = 0;
                    nb -= 1;
                    if nb == 0 {
                        break 'outer;
                    }
                } else {
                    a[dest] = temp[pa].clone();
                    dest += 1;
                    pa += 1;
                    acount += 1;
                    bcount = 0;
                    na -= 1;
                    if na == 1 {
                        // CopyB: the rest of B, then A's last element.
                        clone_within(a, pb, dest, nb);
                        a[dest + nb] = temp[pa].clone();
                        return;
                    }
                }
                if (acount | bcount) >= min_gallop {
                    break;
                }
            }
            min_gallop += 1;
            self.min_gallop = min_gallop;
            // Galloping mode.
            loop {
                min_gallop -= usize::from(min_gallop > 1);
                self.min_gallop = min_gallop;

                let key = a[pb].clone();
                let k = self.gallop_right(&key, &temp[pa..pa + na], 0);
                acount = k;
                if k > 0 {
                    a[dest..dest + k].clone_from_slice(&temp[pa..pa + k]);
                    dest += k;
                    pa += k;
                    na -= k;
                    if na == 1 {
                        clone_within(a, pb, dest, nb);
                        a[dest + nb] = temp[pa].clone();
                        return;
                    }
                    if na == 0 {
                        break 'outer;
                    }
                }
                a[dest] = a[pb].clone();
                dest += 1;
                pb += 1;
                nb -= 1;
                if nb == 0 {
                    break 'outer;
                }

                let key = temp[pa].clone();
                let bslice: Vec<T> = a[pb..pb + nb].to_vec();
                let k = self.gallop_left(&key, &bslice, 0);
                bcount = k;
                if k > 0 {
                    clone_within(a, pb, dest, k);
                    dest += k;
                    pb += k;
                    nb -= k;
                    if nb == 0 {
                        break 'outer;
                    }
                }
                a[dest] = temp[pa].clone();
                dest += 1;
                pa += 1;
                na -= 1;
                if na == 1 {
                    clone_within(a, pb, dest, nb);
                    a[dest + nb] = temp[pa].clone();
                    return;
                }
                if !(acount >= MIN_GALLOP || bcount >= MIN_GALLOP) {
                    break;
                }
            }
            min_gallop += 1; // penalise leaving galloping mode
            self.min_gallop = min_gallop;
        }
        // Succeed: whatever is left of A goes at the end.
        a[dest..dest + na].clone_from_slice(&temp[pa..pa + na]);
    }

    /// CPython `merge_hi`: `B` (the shorter, right run) is copied out and
    /// merged back right to left.  The tie rule is the mirror of `merge_lo`'s
    /// and preserves the same stability.
    ///
    /// Cursors are `isize` on purpose.  C walks these pointers *downward* and
    /// is allowed to step one slot below the base as long as it does not
    /// dereference there; the same arithmetic on `usize` wraps to
    /// `2^64 - 1` and panics on the next index.  That is not hypothetical --
    /// it fired on the very first randomized design of 27 nets.
    fn merge_hi(&mut self, a: &mut [T], base_a: usize, na0: usize, nb0: usize) {
        let lt = self.lt;
        let base_b = base_a + na0;
        let temp: Vec<T> = a[base_b..base_b + nb0].to_vec();
        let mut dest = (base_b + nb0 - 1) as isize; // write cursor, descending
        let mut na = na0;
        let mut nb = nb0;
        let mut pa = (base_a + na0 - 1) as isize; // into a, descending
        let mut pb = (nb0 - 1) as isize; // into temp, descending

        macro_rules! at {
            ($i:expr) => {
                $i as usize
            };
        }
        // CopyA: the rest of A, then B's first element in front of it.
        macro_rules! copy_a {
            () => {{
                for i in 0..na as isize {
                    a[at!(dest - i)] = a[at!(pa - i)].clone();
                }
                a[at!(dest - na as isize)] = temp[at!(pb)].clone();
                return;
            }};
        }
        // Succeed: whatever is left of B goes at the front.
        macro_rules! copy_b_rest {
            () => {{
                for i in 0..nb as isize {
                    a[at!(dest - i)] = temp[at!(pb - i)].clone();
                }
                return;
            }};
        }

        a[at!(dest)] = a[at!(pa)].clone();
        dest -= 1;
        na -= 1;
        if na == 0 {
            copy_b_rest!();
        }
        pa -= 1;
        if nb == 1 {
            copy_a!();
        }

        let mut min_gallop = self.min_gallop;
        loop {
            let mut acount = 0usize;
            let mut bcount = 0usize;
            // One-at-a-time mode.
            loop {
                if lt(&temp[at!(pb)], &a[at!(pa)]) {
                    a[at!(dest)] = a[at!(pa)].clone();
                    dest -= 1;
                    acount += 1;
                    bcount = 0;
                    na -= 1;
                    if na == 0 {
                        copy_b_rest!();
                    }
                    pa -= 1;
                } else {
                    a[at!(dest)] = temp[at!(pb)].clone();
                    dest -= 1;
                    bcount += 1;
                    acount = 0;
                    nb -= 1;
                    if nb == 1 {
                        pb -= 1;
                        copy_a!();
                    }
                    pb -= 1;
                }
                if (acount | bcount) >= min_gallop {
                    break;
                }
            }
            min_gallop += 1;
            self.min_gallop = min_gallop;
            // Galloping mode.
            loop {
                min_gallop -= usize::from(min_gallop > 1);
                self.min_gallop = min_gallop;

                let key = temp[at!(pb)].clone();
                let aslice: Vec<T> = a[at!(pa + 1 - na as isize)..=at!(pa)].to_vec();
                let k = na - self.gallop_right(&key, &aslice, na - 1);
                acount = k;
                if k > 0 {
                    for i in 0..k as isize {
                        a[at!(dest - i)] = a[at!(pa - i)].clone();
                    }
                    dest -= k as isize;
                    pa -= k as isize;
                    na -= k;
                    if na == 0 {
                        copy_b_rest!();
                    }
                }
                a[at!(dest)] = temp[at!(pb)].clone();
                dest -= 1;
                nb -= 1;
                if nb == 1 {
                    pb -= 1;
                    copy_a!();
                }
                pb -= 1;

                let key = a[at!(pa)].clone();
                let bslice: Vec<T> = temp[at!(pb + 1 - nb as isize)..=at!(pb)].to_vec();
                let k = nb - self.gallop_left(&key, &bslice, nb - 1);
                bcount = k;
                if k > 0 {
                    for i in 0..k as isize {
                        a[at!(dest - i)] = temp[at!(pb - i)].clone();
                    }
                    dest -= k as isize;
                    pb -= k as isize;
                    nb -= k;
                    if nb == 1 {
                        copy_a!();
                    }
                    // CPython guards this explicitly, with the comment
                    // "nb==0 is impossible now if the comparison function is
                    // consistent, but we can't assume that it is".  Ours is
                    // not: a NaN wirelength makes the key comparison
                    // inconsistent, and without this guard `pb` walks below
                    // the base of the temp array.  Measured on a 27-net
                    // randomized design.
                    if nb == 0 {
                        copy_b_rest!();
                    }
                }
                a[at!(dest)] = a[at!(pa)].clone();
                dest -= 1;
                na -= 1;
                if na == 0 {
                    copy_b_rest!();
                }
                pa -= 1;
                if !(acount >= MIN_GALLOP || bcount >= MIN_GALLOP) {
                    break;
                }
            }
            min_gallop += 1;
            self.min_gallop = min_gallop;
        }
    }

    /// CPython `merge_at`: merge pending runs `i` and `i+1`.
    ///
    /// The two boundary gallops matter as much as the merge itself: the head
    /// of `A` already below all of `B`, and the tail of `B` already above all
    /// of `A`, are skipped, so only the overlapping middle is merged.
    fn merge_at(&mut self, a: &mut [T], i: usize) {
        let ra = self.pending[i];
        let rb = self.pending[i + 1];
        let mut base_a = ra.base;
        let mut na = ra.len;
        let base_b = rb.base;
        let mut nb = rb.len;

        self.pending[i].len = na + nb;
        let last = self.pending.len() - 1;
        if i == last - 2 {
            self.pending[i + 1] = self.pending[i + 2];
        }
        self.pending.remove(last);

        // Where does B[0] belong in A?
        let key = a[base_b].clone();
        let k = self.gallop_right(&key, &a[base_a..base_a + na], 0);
        base_a += k;
        na -= k;
        if na == 0 {
            return;
        }
        // Where does A[-1] belong in B?
        let key = a[base_a + na - 1].clone();
        nb = self.gallop_left(&key, &a[base_b..base_b + nb], nb - 1);
        if nb == 0 {
            return;
        }
        if na <= nb {
            self.merge_lo(a, base_a, na, nb);
        } else {
            self.merge_hi(a, base_a, na, nb);
        }
    }

    /// CPython `powerloop` (Munro & Wild powersort), which replaced the old
    /// `merge_collapse` length invariants in 3.11.  Works on `2*a` and `2*b`
    /// so the two run midpoints stay integral.
    fn powerloop(s1: usize, n1: usize, n2: usize, n: usize) -> u32 {
        let mut result = 0u32;
        let mut a = 2 * s1 + n1;
        let mut b = a + n1 + n2;
        loop {
            result += 1;
            if a >= n {
                a -= n;
                b -= n;
            } else if b >= n {
                break;
            }
            a <<= 1;
            b <<= 1;
        }
        result
    }

    /// CPython `found_new_run`: before pushing a run of length `n2`, merge
    /// away every pending run whose power exceeds the new boundary's.
    fn found_new_run(&mut self, a: &mut [T], n2: usize) {
        if !self.pending.is_empty() {
            let last = self.pending[self.pending.len() - 1];
            let power = Self::powerloop(last.base, last.len, n2, self.listlen);
            while self.pending.len() > 1 && self.pending[self.pending.len() - 2].power > power {
                let i = self.pending.len() - 2;
                self.merge_at(a, i);
            }
            let n = self.pending.len();
            self.pending[n - 1].power = power;
        }
    }

    /// CPython `merge_force_collapse`: drain the stack at the end.
    fn merge_force_collapse(&mut self, a: &mut [T]) {
        while self.pending.len() > 1 {
            let mut n = self.pending.len() - 2;
            if n > 0 && self.pending[n - 1].len < self.pending[n + 1].len {
                n -= 1;
            }
            self.merge_at(a, n);
        }
    }
}

/// CPython 3.12 `list.sort` for the comparator `lt`.
///
/// A full port -- `count_run`, `binarysort`, `merge_compute_minrun`,
/// `gallop_left`/`gallop_right`, `merge_lo`/`merge_hi` with the adaptive
/// `min_gallop`, and the powersort merge schedule -- rather than a stable
/// sort that happens to agree.
///
/// The distinction is not academic.  An earlier draft used a plain stable
/// merge, on the reasoning that a stable sort is unique whenever the
/// comparator is a strict weak order, and that the corpus's only NaN row is
/// `n = 3`, which never merges.  A randomized harness over 2400 NaN-laden
/// designs disagreed with CPython on **624** of them, the first at `n = 64`
/// -- the exact size at which `minrun` first yields two runs and a merge
/// happens at all.  The corpus alone would never have shown it.
fn py_list_sort<T: Clone>(a: &mut [T], lt: &dyn Fn(&T, &T) -> bool) {
    let n = a.len();
    if n < 2 {
        return;
    }
    let mut ms = MergeState::new(lt, n);
    let minrun = merge_compute_minrun(n);
    let mut lo = 0usize;
    while lo < n {
        let remaining = n - lo;
        let mut run = count_run(&mut a[lo..], lt);
        if run < minrun {
            let force = remaining.min(minrun);
            binarysort(&mut a[lo..lo + force], run, lt);
            run = force;
        }
        ms.found_new_run(a, run);
        ms.pending.push(Run {
            base: lo,
            len: run,
            power: 0,
        });
        lo += run;
    }
    ms.merge_force_collapse(a);
}

// ===========================================================================
// order_nets
// ===========================================================================

struct NetRow {
    name: String,
    pin_count: i64,
    net_class: String,
}

/// `[(name, [(comp_ref, pin_name), ...], net_class_or_None)]`.
///
/// A `None` net class becomes `"Signal"`: the builder leaves `Net.net_class`
/// at its dataclass default, which *is* `"Signal"`, and the oracle's
/// `getattr(net, "net_class", None) or "Signal"` then keeps it.
#[cfg(feature = "python")]
fn parse_nets(nets: &Bound<'_, PyAny>) -> PyResult<Vec<NetRow>> {
    let mut out = Vec::new();
    for row in nets.try_iter()? {
        let row = row?;
        let name: String = row.get_item(0)?.extract()?;
        let pin_count = row.get_item(1)?.len()? as i64;
        let net_class: Option<String> = row.get_item(2)?.extract()?;
        let net_class = match net_class {
            Some(s) if !s.is_empty() => s,
            _ => "Signal".to_string(),
        };
        out.push(NetRow {
            name,
            pin_count,
            net_class,
        });
    }
    Ok(out)
}

/// The oracle's per-net key, in field order.
///
/// Every element is a plain `int`/`float`/`str` here. `order_nets` sources
/// `config_priority` from a `dict[str, int]` or from the literal default 5.
fn order_key(
    net: &NetRow,
    components: &[CompRow],
    loops: &[LoopRow],
    config: &HashMap<String, i64>,
) -> Vec<KeyElem> {
    const DEFAULT_PRIORITY: i64 = 5;
    let config_priority = config.get(&net.name).copied().unwrap_or(DEFAULT_PRIORITY);
    vec![
        KeyElem::Int(config_priority),
        KeyElem::Int(loop_criticality(&net.name, loops)),
        KeyElem::Int(net_class_from_string(&net.net_class)),
        KeyElem::Int(net.pin_count),
        // Each HPWL is a freshly computed value with no Python object
        // behind it, so the identity shortcut cannot fire between two
        // different nets -- exactly as in CPython, where `width + height`
        // allocates a new float every time.
        KeyElem::Float(compute_hpwl(&net.name, components), None),
        KeyElem::Str(net.name.clone()),
    ]
}

// ===========================================================================
// PyO3 surface
// ===========================================================================

/// `net_ordering.get_net_class_from_string(s).value`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn net_class_from_string_py(s: &str) -> i64 {
    net_class_from_string(s)
}

/// `net_ordering.get_loop_criticality(net, build_loops(loop_specs))`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn net_loop_criticality_py(net: &str, loop_specs: &Bound<'_, PyAny>) -> PyResult<i64> {
    let loops = parse_loops(loop_specs)?;
    Ok(loop_criticality(net, &loops))
}

/// `net_ordering.compute_hpwl(net, build_netlist(components))`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn net_compute_hpwl_py(net: &str, components: &Bound<'_, PyAny>) -> PyResult<f64> {
    let comps = parse_components(components)?;
    Ok(compute_hpwl(net, &comps))
}

/// `net_ordering.compute_bbox_area(net, build_netlist(components))`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn net_compute_bbox_area_py(net: &str, components: &Bound<'_, PyAny>) -> PyResult<f64> {
    let comps = parse_components(components)?;
    Ok(compute_bbox_area(net, &comps))
}

/// `net_ordering.order_nets(build_order_netlist(components, nets),
/// build_loops(loop_specs), config)`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn order_nets_py(
    components: &Bound<'_, PyAny>,
    nets: &Bound<'_, PyAny>,
    loop_specs: &Bound<'_, PyAny>,
    config: Option<&Bound<'_, PyDict>>,
) -> PyResult<Vec<String>> {
    let net_rows = parse_nets(nets)?;
    // The oracle's `if not netlist.nets: return []` runs BEFORE any loop is
    // built, so an empty net list must not surface `add_loop`'s ValueError.
    if net_rows.is_empty() {
        return Ok(Vec::new());
    }
    let comps = parse_components(components)?;
    let loops = parse_loops(loop_specs)?;

    let mut cfg: HashMap<String, i64> = HashMap::new();
    if let Some(d) = config {
        for (k, v) in d.iter() {
            cfg.insert(k.extract()?, v.extract()?);
        }
    }

    let mut keyed: Vec<(Vec<KeyElem>, String)> = net_rows
        .iter()
        .map(|n| (order_key(n, &comps, &loops, &cfg), n.name.clone()))
        .collect();

    py_list_sort(&mut keyed, &|x, y| py_key_lt(&x.0, &y.0));

    Ok(keyed.into_iter().map(|(_, name)| name).collect())
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(net_class_from_string_py, m)?)?;
    m.add_function(wrap_pyfunction!(net_loop_criticality_py, m)?)?;
    m.add_function(wrap_pyfunction!(net_compute_hpwl_py, m)?)?;
    m.add_function(wrap_pyfunction!(net_compute_bbox_area_py, m)?)?;
    m.add_function(wrap_pyfunction!(order_nets_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn py_max_is_a_left_to_right_scan_not_f64_max() {
        assert!(py_max(&[f64::NAN, 5.0, 1.0]).is_nan());
        assert_eq!(py_max(&[5.0, f64::NAN, 1.0]), 5.0);
        assert_eq!(py_max(&[1.0, f64::NAN, 5.0]), 5.0);
        assert!(py_min(&[f64::NAN, 5.0]).is_nan());
        assert_eq!(py_min(&[5.0, f64::NAN]), 5.0);
        // f64::max would answer 5.0 for the first case -- the discriminator.
        assert_ne!(
            py_max(&[f64::NAN, 5.0, 1.0]).is_nan(),
            [f64::NAN, 5.0, 1.0]
                .iter()
                .fold(f64::MIN, |a, &b| a.max(b))
                .is_nan()
        );
    }

    #[cfg_attr(test, test)]
    fn quadrant_rotation_is_not_an_exact_axis_swap() {
        let (x, y) = rotate_local_to_world(0.9375, 0.0, normalize_rotation_index(1));
        assert_ne!(x, 0.0, "cos(pi/2) residue was optimised away");
        assert_eq!(y, -0.9375);
        assert_eq!(x, 0.9375 * std::f64::consts::FRAC_PI_2.cos());
    }

    #[cfg_attr(test, test)]
    fn minrun_matches_cpython() {
        assert_eq!(merge_compute_minrun(3), 3);
        assert_eq!(merge_compute_minrun(63), 63);
        assert_eq!(merge_compute_minrun(64), 32);
        assert_eq!(merge_compute_minrun(65), 33);
        assert_eq!(merge_compute_minrun(1000), 63);
        assert_eq!(merge_compute_minrun(1024), 32);
    }

    #[cfg_attr(test, test)]
    fn count_run_reverses_only_strictly_descending_runs() {
        let lt = |a: &i32, b: &i32| a < b;
        let mut a = vec![3, 2, 1, 5];
        assert_eq!(count_run(&mut a, &lt), 3);
        assert_eq!(a, vec![1, 2, 3, 5]);
        // equal neighbours end an ascending run only when strictly less
        let mut b = vec![1, 1, 2, 0];
        assert_eq!(count_run(&mut b, &lt), 3);
        assert_eq!(b, vec![1, 1, 2, 0]);
    }

    #[cfg_attr(test, test)]
    fn binarysort_is_stable() {
        let lt = |a: &(i32, char), b: &(i32, char)| a.0 < b.0;
        let mut a = vec![(1, 'a'), (1, 'b'), (0, 'c'), (1, 'd')];
        binarysort(&mut a, 1, &lt);
        assert_eq!(a, vec![(0, 'c'), (1, 'a'), (1, 'b'), (1, 'd')]);
    }

    /// The oracle's measured answer for the `nan_wirelength` corpus row and
    /// its 6 permutations: 4 distinct orderings, captured from CPython.
    #[cfg_attr(test, test)]
    fn nan_keys_reproduce_cpython_sort_placement() {
        let key = |wl: f64, name: &str| {
            vec![
                KeyElem::Int(5),
                KeyElem::Int(3),
                KeyElem::Int(4),
                KeyElem::Int(2),
                KeyElem::Float(wl, None),
                KeyElem::Str(name.to_string()),
            ]
        };
        let rows = [("P", 2.0), ("Q", f64::NAN), ("R", 4.0)];
        let expected: &[(&[usize], [&str; 3])] = &[
            (&[0, 1, 2], ["P", "Q", "R"]),
            (&[0, 2, 1], ["P", "R", "Q"]),
            (&[1, 0, 2], ["Q", "P", "R"]),
            (&[1, 2, 0], ["Q", "P", "R"]),
            (&[2, 0, 1], ["P", "R", "Q"]),
            (&[2, 1, 0], ["R", "Q", "P"]),
        ];
        for (perm, want) in expected {
            let mut v: Vec<(Vec<KeyElem>, String)> = perm
                .iter()
                .map(|&i| (key(rows[i].1, rows[i].0), rows[i].0.to_string()))
                .collect();
            py_list_sort(&mut v, &|x, y| py_key_lt(&x.0, &y.0));
            let got: Vec<String> = v.into_iter().map(|(_, n)| n).collect();
            assert_eq!(got, want.to_vec(), "permutation {perm:?}");
        }
    }

    #[cfg_attr(test, test)]
    fn net_class_lookup_is_exact_match_only() {
        assert_eq!(net_class_from_string("GND"), 5);
        assert_eq!(net_class_from_string("gnd"), 4, "case-insensitive lookup");
        assert_eq!(net_class_from_string(" GND"), 4, "trimmed lookup");
        assert_eq!(net_class_from_string("GND2"), 4, "prefix lookup");
        assert_eq!(net_class_from_string(""), 4);
    }

    #[cfg_attr(test, test)]
    fn identity_shortcut_makes_the_same_nan_object_equal() {
        let same = KeyElem::Float(f64::NAN, Some(0xdead));
        let other = KeyElem::Float(f64::NAN, Some(0xdead));
        assert!(py_eq_elem(&same, &other), "identity shortcut lost");
        let distinct_a = KeyElem::Float(f64::NAN, Some(1));
        let distinct_b = KeyElem::Float(f64::NAN, Some(2));
        let no_ids_a = KeyElem::Float(f64::NAN, None);
        let no_ids_b = KeyElem::Float(f64::NAN, None);
        assert!(!py_eq_elem(&no_ids_a, &no_ids_b), "None ids must not alias");
        assert!(!py_eq_elem(&distinct_a, &distinct_b));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("net_ordering::tests::py_max_is_a_left_to_right_scan_not_f64_max", py_max_is_a_left_to_right_scan_not_f64_max),
        ("net_ordering::tests::quadrant_rotation_is_not_an_exact_axis_swap", quadrant_rotation_is_not_an_exact_axis_swap),
        ("net_ordering::tests::minrun_matches_cpython", minrun_matches_cpython),
        ("net_ordering::tests::count_run_reverses_only_strictly_descending_runs", count_run_reverses_only_strictly_descending_runs),
        ("net_ordering::tests::binarysort_is_stable", binarysort_is_stable),
        ("net_ordering::tests::nan_keys_reproduce_cpython_sort_placement", nan_keys_reproduce_cpython_sort_placement),
        ("net_ordering::tests::net_class_lookup_is_exact_match_only", net_class_lookup_is_exact_match_only),
        ("net_ordering::tests::identity_shortcut_makes_the_same_nan_object_equal", identity_shortcut_makes_the_same_nan_object_equal),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
