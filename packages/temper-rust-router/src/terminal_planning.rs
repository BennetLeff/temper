//! Wave-4 terminal-tree slice: `router_v6/terminal_extraction` and
//! `router_v6/terminal_tree` in Rust.
//!
//! Mirrors, bit for bit, the two pinned Python oracles:
//! `packages/temper-placer/tests/router_v6/_terminal_extraction_py_oracle.py`,
//! `_terminal_tree_py_oracle.py` -- each a
//! verbatim `git show` extraction of its module at
//! `550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5` (`origin/main`), which is
//! character-identical to `origin/main` at the time this module was written
//! (`git diff 550cab2a3a HEAD -- .../{terminal_extraction,terminal_tree}.py`
//! is empty).
//!
//! Why this crate
//! --------------
//! Both modules are Router V6 topology/export planning, not shared
//! geometry primitives -- `temper-rust-router` already owns
//! `net_ordering.rs`, the closest sibling kernel (also a total-order
//! comparator over router-local data), so this module follows the same
//! shape: pure logic and its `#[pyfunction]` surface together in one file
//! in the pyo3 crate, rather than split across a `-core` crate. Per the
//! migration brief, `temper-geometry` and `temper-thermal` are explicitly
//! out of scope for this slice (concurrent agents own their `lib.rs`).
//!
//! Semantics that are NOT the obvious Rust ones
//! ---------------------------------------------
//! * `terminal_tree.py::plan_terminal_tree` builds `remaining = set(...)`
//!   and iterates `connected`/`remaining` as Python `set`s (hash-order
//!   dependent, PEP 456 salted per process) -- but the `min(key=...)`
//!   tie-break key embeds the full candidate `PadIdentity` VALUES, not
//!   just their hash-derived position, and the candidate pool is deduped
//!   by identity first. Two distinct `(source, target)` pairs therefore
//!   never share a key, so CPython's set iteration order never has a tie
//!   to resolve and this kernel's ascending-index iteration (see
//!   [`plan_terminal_tree`]) reproduces the oracle exactly -- see the
//!   oracle module's own docstring for the full argument and
//!   `test_trap_hash_order_does_not_leak_into_output`-class evidence.
//! * `terminal_extraction.py::extract_net_terminals` calls
//!   `pin_world_position` (`core/pin_geometry.py`, R(-theta) --
//!   `geometry/kicad_transform.py`'s documented KiCad footprint-child
//!   convention, NOT R(+theta)) and `pin_world_layer`, never
//!   `pin_world_radius` -- so `roundrect_ratio`/`shape` are correctly
//!   absent from this kernel's wire format; see [`pin_world_position`]'s
//!   own doc comment for the full field list this kernel reads.
//!   `rotate_local_to_world` is NOT special-cased for quadrant angles
//!   (`cos(pi/2)` is `6.123233995736766e-17`, not exactly `0`) --
//!   preserved exactly as `net_ordering.rs`'s sibling copy of this same
//!   formula documents.
//! * `Component.initial_rotation_quadrant` is typed `int | None` in
//!   `core/netlist.py`'s installed dataclass contract, but
//!   [`rot_to_radians`] reproduces `_normalize_rotation`'s full three-way
//!   dispatch anyway, as does `net_ordering.rs`'s sibling copy: `None` is
//!   `0.0`, an **int is a quarter-turn INDEX** scaled by `PI/2`, and a
//!   **float is already RADIANS** and passes through untouched.
//!
//!   This module used to argue the reverse -- that the float branch is
//!   unreachable through the real object model, so binding the value as
//!   `Option<i64>` was safe. The contract claim is true; the conclusion was
//!   not, because the CANONICAL kernel (`temper_geometry`'s
//!   `normalize_rotation_py` / `rot_to_radians`) takes `&Bound<'_, PyAny>`
//!   and accepts "None, int, or float" -- so the declared contract and the
//!   canonical implementation disagree, and this kernel was quietly siding
//!   with the narrower one. `escape_via.rs` made exactly that bet and lost:
//!   pyo3 REJECTS a non-integral float rather than truncating, so a
//!   fractional rotation raised `TypeError` instead of producing an angle.
//!
//!   Note that merely WIDENING the binding to `Option<f64>` does not fix
//!   this -- it accepts the float and then multiplies it by `PI/2`, reading
//!   radians as an index. That substitutes a quiet wrong number for a loud
//!   `TypeError`; the supplemental regression in
//!   `test_net_ordering_rust_supplemental.py` catches it. Reproducing the
//!   dispatch is what actually fixes it.
//! * `sorted(terminals, key=lambda t: t.identity)` in
//!   `extract_net_terminals` is CPython's stable timsort. This module uses
//!   `Vec::sort_by`, which the Rust standard library also guarantees
//!   stable -- `sort_unstable_by` would diverge on ties (duplicate
//!   `(component_ref, pad)` entries in `net_pins` produce a genuine tie on
//!   the full `PadIdentity` key, and Python's `sorted()` preserves their
//!   relative input order in that case).

use std::cmp::Ordering;
use std::collections::HashMap;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyAny;

// ===========================================================================
// terminal_tree.py
// ===========================================================================

/// `PadIdentity` -- `(component_ref, pad, net, x, y, layers)`, matching
/// `router_v6/connectivity.py`'s `@dataclass(frozen=True, order=True)`
/// field order exactly.
#[derive(Debug, Clone)]
struct PadIdentity {
    component_ref: String,
    pad: String,
    net: String,
    x: f64,
    y: f64,
    layers: Vec<i64>,
}

/// `PadIdentity.__eq__` -- CPython dataclass equality is a field-tuple
/// `==`, including `NaN != NaN` for the float fields. Mirrored exactly
/// (not `to_bits()` equality) so two independently-NaN identities never
/// dedup against each other here, just as they never would in the Python
/// dict comprehension this function replaces.
fn identity_eq(a: &PadIdentity, b: &PadIdentity) -> bool {
    a.component_ref == b.component_ref
        && a.pad == b.pad
        && a.net == b.net
        && a.x == b.x
        && a.y == b.y
        && a.layers == b.layers
}

/// `PadIdentity.__lt__`/`order=True` -- a plain field-tuple lexicographic
/// compare. `f64::total_cmp` (not `partial_cmp().unwrap()`, forbidden by
/// this crate's `expect_used`/`unwrap_used` lints) gives a total order
/// that agrees with Python's `<` everywhere x/y are not NaN -- the only
/// domain real pad coordinates occupy.
fn identity_cmp(a: &PadIdentity, b: &PadIdentity) -> Ordering {
    a.component_ref
        .cmp(&b.component_ref)
        .then_with(|| a.pad.cmp(&b.pad))
        .then_with(|| a.net.cmp(&b.net))
        .then_with(|| a.x.total_cmp(&b.x))
        .then_with(|| a.y.total_cmp(&b.y))
        .then_with(|| a.layers.cmp(&b.layers))
}

struct TreePad {
    identity: PadIdentity,
    center: (f64, f64),
}

/// `terminal_tree._manhattan`. Deliberately `abs` + `abs`, NOT
/// `math.hypot` and NOT `sqrt(dx*dx + dy*dy)`.
fn manhattan(a: &TreePad, b: &TreePad) -> f64 {
    (a.center.0 - b.center.0).abs() + (a.center.1 - b.center.1).abs()
}

struct TerminalTreePlan {
    root: PadIdentity,
    edges: Vec<(PadIdentity, PadIdentity)>,
}

/// `terminal_tree.plan_terminal_tree`.
///
/// `pads` is deduped by identity first (later entry's VALUE wins, but
/// position is fixed at first occurrence -- `{pad.identity: pad for pad in
/// pads}`'s exact dict-comprehension semantics), then the root is the
/// lexicographically smallest identity, then a Prim-style attach loop picks
/// the globally minimal `(manhattan_distance, source_identity,
/// target_identity)` triple at each step. See this module's own docstring
/// for why plain ascending-index iteration over the connected/remaining
/// partition reproduces CPython's hash-ordered `set` iteration exactly for
/// this specific key shape.
fn plan_terminal_tree(pads: &[TreePad]) -> Result<TerminalTreePlan, String> {
    let mut uniq: Vec<TreePad> = Vec::new();
    for pad in pads {
        if let Some(existing) = uniq
            .iter_mut()
            .find(|p| identity_eq(&p.identity, &pad.identity))
        {
            existing.center = pad.center;
            // identity fields are equal by construction (identity_eq),
            // but the PadIdentity object stored is the FIELD VALUES of
            // the newest pad, matching the dict comprehension's "value is
            // the last write" semantics precisely.
            existing.identity = PadIdentity {
                component_ref: pad.identity.component_ref.clone(),
                pad: pad.identity.pad.clone(),
                net: pad.identity.net.clone(),
                x: pad.identity.x,
                y: pad.identity.y,
                layers: pad.identity.layers.clone(),
            };
        } else {
            uniq.push(TreePad {
                identity: PadIdentity {
                    component_ref: pad.identity.component_ref.clone(),
                    pad: pad.identity.pad.clone(),
                    net: pad.identity.net.clone(),
                    x: pad.identity.x,
                    y: pad.identity.y,
                    layers: pad.identity.layers.clone(),
                },
                center: pad.center,
            });
        }
    }

    if uniq.is_empty() {
        return Err("terminal tree requires at least one pad".to_string());
    }

    // root = min(terminals) -- first-occurrence order, first minimal wins.
    let mut root_idx = 0usize;
    for i in 1..uniq.len() {
        if identity_cmp(&uniq[i].identity, &uniq[root_idx].identity) == Ordering::Less {
            root_idx = i;
        }
    }

    let n = uniq.len();
    let mut connected = vec![false; n];
    connected[root_idx] = true;
    let mut num_connected = 1usize;
    let mut edges: Vec<(usize, usize)> = Vec::new();

    while num_connected < n {
        let mut best: Option<(usize, usize)> = None;
        for i in 0..n {
            if !connected[i] {
                continue;
            }
            for (j, &target_connected) in connected.iter().enumerate() {
                if target_connected {
                    continue;
                }
                let better = match best {
                    None => true,
                    Some((bi, bj)) => {
                        edge_cmp(&uniq, i, j, bi, bj) == Ordering::Less
                    }
                };
                if better {
                    best = Some((i, j));
                }
            }
        }
        let (si, ti) = match best {
            Some(pair) => pair,
            None => break, // unreachable: num_connected < n guarantees a candidate
        };
        edges.push((si, ti));
        connected[ti] = true;
        num_connected += 1;
    }

    Ok(TerminalTreePlan {
        root: uniq[root_idx].identity.clone(),
        edges: edges
            .into_iter()
            .map(|(i, j)| (uniq[i].identity.clone(), uniq[j].identity.clone()))
            .collect(),
    })
}

/// Compares candidate edges `(i, j)` vs `(bi, bj)` by the oracle's
/// `key=lambda pair: (_manhattan(...), pair[0], pair[1])`.
fn edge_cmp(uniq: &[TreePad], i: usize, j: usize, bi: usize, bj: usize) -> Ordering {
    let d_ij = manhattan(&uniq[i], &uniq[j]);
    let d_best = manhattan(&uniq[bi], &uniq[bj]);
    d_ij.total_cmp(&d_best)
        .then_with(|| identity_cmp(&uniq[i].identity, &uniq[bi].identity))
        .then_with(|| identity_cmp(&uniq[j].identity, &uniq[bj].identity))
}

// ===========================================================================
// terminal_extraction.py
// ===========================================================================

struct PinRow {
    name: String,
    number: String,
    position: (f64, f64),
    is_pth: bool,
    layer: Option<String>,
}

struct ComponentRow {
    component_ref: String,
    initial_position: Option<(f64, f64)>,
    /// `_normalize_rotation(initial_rotation_quadrant)` -- RESOLVED RADIANS, not the
    /// raw index; the int/float dispatch needs the live Python object.
    initial_rotation_rad: f64,
    initial_side: Option<i64>,
    pins: Vec<PinRow>,
}

struct StackupLayerRow {
    name: Option<String>,
    index: Option<i64>,
    layer_type: Option<String>,
}

struct TerminalRow {
    component_ref: String,
    pad: String,
    net: String,
    x: f64,
    y: f64,
    layers: Vec<i64>,
    layer_names: Vec<Option<String>>,
    is_pth: bool,
}

/// `core/pin_geometry._normalize_rotation`'s **integer-index** branch.
fn normalize_rotation_index(index: i64) -> f64 {
    (index as f64) * std::f64::consts::PI / 2.0
}

/// `core/pin_geometry._normalize_rotation`, whole dispatch. Mirrors
/// `temper_geometry`'s `rot_to_radians` -- see `net_ordering.rs`'s copy of
/// this function for the full reasoning, which applies here identically:
///
/// ```text
/// None  -> 0.0
/// int   -> index * PI / 2      (a quarter-turn INDEX)
/// float -> as-is               (already RADIANS)
/// ```
///
/// This module previously bound the value as `Option<i64>`, arguing the float
/// branch was "unreachable through `Component.initial_rotation_quadrant`'s real
/// `int | None` contract". The contract claim is true -- `core/netlist.py`
/// does declare it -- but the canonical kernel accepts float anyway, so the
/// declared contract and the canonical implementation disagreed and this
/// kernel sided with the narrower one. pyo3 REJECTS a non-integral float on an
/// `i64` extract rather than truncating, which is how the same shape became a
/// real `TypeError` defect in `escape_via.rs`.
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

/// `geometry/kicad_transform.rotate_local_to_world` -- R(-theta), KiCad's
/// real footprint-child rotation convention. Deliberately NOT
/// special-cased for quadrant angles.
fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let c = theta_rad.cos();
    let s = theta_rad.sin();
    (x * c + y * s, -x * s + y * c)
}

/// `core/pin_geometry.pin_world_position` (via `pin_world_position_at`
/// with no overrides -- `extract_net_terminals` never passes any).
///
/// Reads exactly: `pin.position`, `comp.initial_rotation_quadrant`,
/// `comp.initial_side`, `comp.initial_position`. `comp.initial_side or 0`
/// folds `None` to `0`, mirroring only side `1` (bottom) into an X mirror.
/// `comp.initial_position or (0.0, 0.0)` only ever fires on `None` -- a
/// non-`None` 2-tuple, even `(0.0, 0.0)` itself, is never falsy in Python.
fn pin_world_position(pin: &PinRow, comp: &ComponentRow) -> (f64, f64) {
    let rotation_rad = comp.initial_rotation_rad;
    let side = comp.initial_side.unwrap_or(0);
    let (mut px, py) = pin.position;
    if side == 1 {
        px = -px;
    }
    let (rx, ry) = rotate_local_to_world(px, py, rotation_rad);
    let cpos = comp.initial_position.unwrap_or((0.0, 0.0));
    (cpos.0 + rx, cpos.1 + ry)
}

/// `core/pin_geometry.pin_world_layer` -- `getattr(pin, "layer", None) or
/// "F.Cu"`. An empty string is ALSO falsy in Python, so it defaults too,
/// not just `None`/missing.
fn pin_world_layer(pin: &PinRow) -> String {
    match &pin.layer {
        Some(l) if !l.is_empty() => l.clone(),
        _ => "F.Cu".to_string(),
    }
}

/// `PadIdentity`/`ParsedTerminal` field-tuple order:
/// `(component_ref, pad, net, x, y, layers)`.
fn terminal_identity_cmp(a: &TerminalRow, b: &TerminalRow) -> Ordering {
    a.component_ref
        .cmp(&b.component_ref)
        .then_with(|| a.pad.cmp(&b.pad))
        .then_with(|| a.net.cmp(&b.net))
        .then_with(|| a.x.total_cmp(&b.x))
        .then_with(|| a.y.total_cmp(&b.y))
        .then_with(|| a.layers.cmp(&b.layers))
}

/// `terminal_extraction.extract_net_terminals`.
fn extract_net_terminals(
    net_name: &str,
    net_pins: &[(String, String)],
    components: &[ComponentRow],
    stackup_layers: &[StackupLayerRow],
) -> Vec<TerminalRow> {
    // `components = {component.ref: component for component in ...}` --
    // last-ref-wins dict comprehension. Used only for point lookups below
    // (never iterated), so no hash-order leak.
    let mut comp_by_ref: HashMap<&str, usize> = HashMap::new();
    for (idx, c) in components.iter().enumerate() {
        comp_by_ref.insert(c.component_ref.as_str(), idx);
    }

    // `layer_indices = {layer.name: layer.index for layer in stackup_layers
    // if layer.name is not None and layer.index is not None}`.
    let mut layer_indices: HashMap<&str, i64> = HashMap::new();
    for layer in stackup_layers {
        if let (Some(name), Some(index)) = (&layer.name, layer.index) {
            layer_indices.insert(name.as_str(), index);
        }
    }

    // `pth_layers = tuple(layer.name for layer in stackup_layers if
    // layer.layer_type in {"signal", "mixed"})` -- ordered, NOT deduped,
    // and NOT filtered on name being non-None (unlike layer_indices above).
    let pth_layers: Vec<Option<String>> = stackup_layers
        .iter()
        .filter(|l| matches!(l.layer_type.as_deref(), Some("signal") | Some("mixed")))
        .map(|l| l.name.clone())
        .collect();

    let mut terminals: Vec<TerminalRow> = Vec::new();
    for (component_ref, pad_name) in net_pins {
        let comp_idx = match comp_by_ref.get(component_ref.as_str()) {
            Some(&i) => i,
            None => continue,
        };
        let comp = &components[comp_idx];

        // `component.get_pin(pad_name)` -- first pin whose `.name` OR
        // `.number` equals `pad_name`, in pin-list order
        // (temper-design-bundle's `Component::get_pin`).
        let pin = match comp
            .pins
            .iter()
            .find(|p| &p.name == pad_name || &p.number == pad_name)
        {
            Some(p) => p,
            None => continue,
        };

        let (x, y) = pin_world_position(pin, comp);
        let is_pth = pin.is_pth;
        let layer_names: Vec<Option<String>> = if is_pth {
            pth_layers.clone()
        } else {
            vec![Some(pin_world_layer(pin))]
        };
        let mut layer_ids: Vec<i64> = layer_names
            .iter()
            .filter_map(|name| name.as_deref().and_then(|n| layer_indices.get(n).copied()))
            .collect();
        layer_ids.sort();

        terminals.push(TerminalRow {
            component_ref: component_ref.clone(),
            pad: pin.number.clone(),
            net: net_name.to_string(),
            x,
            y,
            layers: layer_ids,
            layer_names,
            is_pth,
        });
    }

    // `tuple(sorted(terminals, key=lambda terminal: terminal.identity))`.
    // `sort_by` is stable (Rust guarantees it), matching CPython's
    // timsort stability for the genuine-tie case (duplicate `(ref, pad)`
    // entries in `net_pins`).
    terminals.sort_by(terminal_identity_cmp);
    terminals
}

// ===========================================================================
// PyO3 surface
// ===========================================================================

#[cfg(feature = "python")]
type IdentityTuple = (String, String, String, f64, f64, Vec<i64>);
#[cfg(feature = "python")]
type PadWire = (String, String, String, f64, f64, Vec<i64>, f64, f64);

#[cfg(feature = "python")]
fn identity_to_tuple(i: PadIdentity) -> IdentityTuple {
    (i.component_ref, i.pad, i.net, i.x, i.y, i.layers)
}

/// `terminal_tree.plan_terminal_tree`.
///
/// `pads` is `[(component_ref, pad, net, x, y, layers, center_x,
/// center_y), ...]`. Returns `(root, edges)` where `root` is an identity
/// tuple and `edges` is a list of `(source, target)` identity-tuple
/// pairs -- matching `TerminalTreePlan`/`TerminalTreeEdge`'s field shape
/// so the shipped Python wrapper can reconstruct the dataclasses directly.
#[cfg(feature = "python")]
#[pyfunction]
pub fn plan_terminal_tree_py(
    pads: Vec<PadWire>,
) -> PyResult<(IdentityTuple, Vec<(IdentityTuple, IdentityTuple)>)> {
    let pads: Vec<TreePad> = pads
        .into_iter()
        .map(|(component_ref, pad, net, x, y, layers, cx, cy)| TreePad {
            identity: PadIdentity {
                component_ref,
                pad,
                net,
                x,
                y,
                layers,
            },
            center: (cx, cy),
        })
        .collect();

    let plan = plan_terminal_tree(&pads).map_err(PyValueError::new_err)?;
    Ok((
        identity_to_tuple(plan.root),
        plan.edges
            .into_iter()
            .map(|(s, t)| (identity_to_tuple(s), identity_to_tuple(t)))
            .collect(),
    ))
}

#[cfg(feature = "python")]
type TerminalTuple = (String, String, String, f64, f64, Vec<i64>, Vec<Option<String>>, bool);

/// `terminal_extraction.extract_net_terminals`.
///
/// `components` is a list of ``temper_design_bundle_python.Component``
/// pyclass instances (each with `.ref`, `.initial_position`,
/// `.initial_rotation_quadrant`, `.initial_side`, `.pins` attributes).  Each
/// pin is a ``temper_design_bundle_python.Pin`` pyclass (`.name`,
/// `.number`, `.position`, `.is_pth`, `.layer`).  `stackup_layers`
/// is a list of layer objects (each with `.name`, `.index`,
/// `.layer_type` attributes).  Returns a list of
/// `(component_ref, pad, net, x, y, layers, layer_names, is_pth)`
/// rows, sorted exactly as the oracle's `sorted(terminals, key=...)`.
///
/// Wave-4 marshalling migration: this function now accepts the
/// typed pyclass objects directly and extracts their attributes by
/// name (``.getattr("ref")`` etc.), eliminating the Python-side
/// ``_pin_wire`` / ``_component_wire`` / ``_stackup_layer_wire``
/// wire-format marshalling helpers.
#[cfg(feature = "python")]
#[pyfunction]
pub fn extract_net_terminals_py(
    net_name: &str,
    net_pins: Vec<(String, String)>,
    components: &Bound<'_, PyAny>,
    stackup_layers: &Bound<'_, PyAny>,
) -> PyResult<Vec<TerminalTuple>> {
    let mut comp_rows: Vec<ComponentRow> = Vec::new();
    for row in components.try_iter()? {
        let row = row?;
        let component_ref: String = row.getattr("ref")?.extract()?;
        let initial_position: Option<(f64, f64)> = row.getattr("initial_position")?.extract()?;
        let initial_rotation_rad = rot_to_radians(&row.getattr("initial_rotation_quadrant")?)?;
        let initial_side: Option<i64> = row.getattr("initial_side")?.extract()?;
        let mut pins: Vec<PinRow> = Vec::new();
        for prow in row.getattr("pins")?.try_iter()? {
            let prow = prow?;
            pins.push(PinRow {
                name: prow.getattr("name")?.extract()?,
                number: prow.getattr("number")?.extract()?,
                position: prow.getattr("position")?.extract()?,
                is_pth: prow.getattr("is_pth")?.extract()?,
                layer: prow.getattr("layer")?.extract()?,
            });
        }
        comp_rows.push(ComponentRow {
            component_ref,
            initial_position,
            initial_rotation_rad,
            initial_side,
            pins,
        });
    }

    let mut stackup_rows: Vec<StackupLayerRow> = Vec::new();
    for row in stackup_layers.try_iter()? {
        let row = row?;
        stackup_rows.push(StackupLayerRow {
            name: row.getattr("name")?.extract()?,
            index: row.getattr("index")?.extract()?,
            layer_type: row.getattr("layer_type")?.extract()?,
        });
    }

    let terminals = extract_net_terminals(net_name, &net_pins, &comp_rows, &stackup_rows);
    Ok(terminals
        .into_iter()
        .map(|t| {
            (
                t.component_ref,
                t.pad,
                t.net,
                t.x,
                t.y,
                t.layers,
                t.layer_names,
                t.is_pth,
            )
        })
        .collect())
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(plan_terminal_tree_py, m)?)?;
    m.add_function(wrap_pyfunction!(extract_net_terminals_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
// --- BEGIN generated by scripts/gen_oracle_freeze.py: terminal_tree ---
    /// Frozen golden vectors for `plan_terminal_tree` (FREEZE, U4/U5, batch 3).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec terminal_tree`
    /// (requires reviving the deleted oracle from git history first -- see
    /// scripts/oracle_freeze_specs/terminal_tree.py's module docstring).
    /// Expected identities are stored as INDICES into the case's pad list;
    /// `expected_error` is Some for the empty-input ValueError case.
    pub(crate) mod frozen_terminal_tree_tests {
        use super::*;

        struct FrozenPad {
            component_ref: &'static str,
            pad: &'static str,
            net: &'static str,
            x: f64,
            y: f64,
            layers: &'static [i64],
            center_x: f64,
            center_y: f64,
        }

        struct FrozenTerminalTreeCase {
            name: &'static str,
            tags: &'static [&'static str],
            pads: &'static [FrozenPad],
            expected_root: usize,
            expected_edges: &'static [(usize, usize)],
            expected_error: Option<&'static str>,
        }

        const FROZEN_TERMINAL_TREE_GOLDEN: &[FrozenTerminalTreeCase] = &[
            FrozenTerminalTreeCase {
                name: "three_pad_line",
                tags: &["named:three_pad_line", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0), (1, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "single_pad",
                tags: &["named:single_pad", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "two_pads",
                tags: &["named:two_pads"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4008000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4008000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "star",
                tags: &["large_pad_count", "named:star", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (0, 2), (0, 3), (0, 4)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "multi_component",
                tags: &["multi_component", "named:multi_component", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4034000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4034000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4034000000000000_u64),
                        y: f64::from_bits(0x4034000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4034000000000000_u64),
                        center_y: f64::from_bits(0x4034000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "C1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4034000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4034000000000000_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 2), (3, 0), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "tied_distances",
                tags: &["multi_component", "named:tied_distances", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "A",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "B",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "C",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "negative_and_fractional",
                tags: &["fractional_coord", "named:negative_and_fractional", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xBFF8000000000000_u64),
                        y: f64::from_bits(0xC002000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF8000000000000_u64),
                        center_y: f64::from_bits(0xC002000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x400E000000000000_u64),
                        y: f64::from_bits(0x3FE0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x400E000000000000_u64),
                        center_y: f64::from_bits(0x3FE0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xBFD0000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFD0000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "multi_layer_identity",
                tags: &["multi_layer", "named:multi_layer_identity", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[31],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "duplicate_identity",
                tags: &["duplicate_identity", "named:duplicate_identity", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "empty_raises",
                tags: &["empty", "named:empty_raises"],
                pads: &[
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: Some("terminal tree requires at least one pad"),
            },
            FrozenTerminalTreeCase {
                name: "grid_3x3",
                tags: &["large_pad_count", "named:grid_3x3", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "8",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (0, 3), (1, 2), (1, 4), (2, 5), (3, 6), (4, 7), (5, 8)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "duplicate_identity_divergent_center",
                tags: &["duplicate_identity", "named:duplicate_identity_divergent_center", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_0",
                tags: &["fractional_coord", "multi_component", "named:rand_0", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x404FB353F7CED917_u64),
                        y: f64::from_bits(0xC04645604189374C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404FB353F7CED917_u64),
                        center_y: f64::from_bits(0xC04645604189374C_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x40562CDD2F1A9FBE_u64),
                        y: f64::from_bits(0xC041E6872B020C4A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40562CDD2F1A9FBE_u64),
                        center_y: f64::from_bits(0xC041E6872B020C4A_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x403B1FBE76C8B439_u64),
                        y: f64::from_bits(0xC043DED916872B02_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403B1FBE76C8B439_u64),
                        center_y: f64::from_bits(0xC043DED916872B02_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_1",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_1", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC045F3B645A1CAC1_u64),
                        y: f64::from_bits(0xC0420DD2F1A9FBE7_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC045F3B645A1CAC1_u64),
                        center_y: f64::from_bits(0xC0420DD2F1A9FBE7_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0xC010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0xC010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC04390C49BA5E354_u64),
                        y: f64::from_bits(0xC0352872B020C49C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04390C49BA5E354_u64),
                        center_y: f64::from_bits(0xC0352872B020C49C_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x4041ADB22D0E5604_u64),
                        y: f64::from_bits(0xC0364A3D70A3D70A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4041ADB22D0E5604_u64),
                        center_y: f64::from_bits(0xC0364A3D70A3D70A_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (2, 5), (2, 4), (5, 6), (5, 3), (3, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_2",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_2", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC04333126E978D50_u64),
                        y: f64::from_bits(0xC0557D1EB851EB85_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04333126E978D50_u64),
                        center_y: f64::from_bits(0xC0557D1EB851EB85_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC03BB0E560418937_u64),
                        y: f64::from_bits(0x4040C2F1A9FBE76D_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC03BB0E560418937_u64),
                        center_y: f64::from_bits(0x4040C2F1A9FBE76D_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x40512F9DB22D0E56_u64),
                        y: f64::from_bits(0x40522989374BC6A8_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x40512F9DB22D0E56_u64),
                        center_y: f64::from_bits(0x40522989374BC6A8_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC0423CCCCCCCCCCD_u64),
                        y: f64::from_bits(0x4056D9EB851EB852_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0423CCCCCCCCCCD_u64),
                        center_y: f64::from_bits(0x4056D9EB851EB852_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                ],
                expected_root: 6,
                expected_edges: &[(6, 7), (6, 4), (4, 3), (6, 1), (1, 5), (5, 2), (1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_3",
                tags: &["named:rand_3", "negative_coord", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_4",
                tags: &["fractional_coord", "multi_component", "named:rand_4", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC04E1810624DD2F2_u64),
                        y: f64::from_bits(0x4035CA7EF9DB22D1_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04E1810624DD2F2_u64),
                        center_y: f64::from_bits(0x4035CA7EF9DB22D1_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x402D774BC6A7EF9E_u64),
                        y: f64::from_bits(0x4058C75C28F5C28F_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x402D774BC6A7EF9E_u64),
                        center_y: f64::from_bits(0x4058C75C28F5C28F_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4031A083126E978D_u64),
                        y: f64::from_bits(0xC04D0353F7CED917_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4031A083126E978D_u64),
                        center_y: f64::from_bits(0xC04D0353F7CED917_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 3), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_5",
                tags: &["fractional_coord", "multi_component", "named:rand_5", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x404813B645A1CAC1_u64),
                        y: f64::from_bits(0x40525A8F5C28F5C3_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404813B645A1CAC1_u64),
                        center_y: f64::from_bits(0x40525A8F5C28F5C3_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0582E6666666666_u64),
                        y: f64::from_bits(0xC058AD3F7CED9168_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0582E6666666666_u64),
                        center_y: f64::from_bits(0xC058AD3F7CED9168_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_6",
                tags: &["fractional_coord", "multi_component", "named:rand_6", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC0541B3333333333_u64),
                        y: f64::from_bits(0xC036A4DD2F1A9FBE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0541B3333333333_u64),
                        center_y: f64::from_bits(0xC036A4DD2F1A9FBE_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x40164AC083126E98_u64),
                        y: f64::from_bits(0x4050E5604189374C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40164AC083126E98_u64),
                        center_y: f64::from_bits(0x4050E5604189374C_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (2, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_7",
                tags: &["duplicate_identity", "fractional_coord", "multi_component", "named:rand_7", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x402D083126E978D5_u64),
                        y: f64::from_bits(0x4056E03126E978D5_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x402D083126E978D5_u64),
                        center_y: f64::from_bits(0x4056E03126E978D5_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 3), (3, 0), (1, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_8",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_8", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0xC022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0xC022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0x4008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0x4008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x4050B872B020C49C_u64),
                        y: f64::from_bits(0xC0526C189374BC6A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4050B872B020C49C_u64),
                        center_y: f64::from_bits(0xC0526C189374BC6A_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (2, 3), (1, 5), (5, 4), (4, 0), (0, 6)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_9",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_9", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4054E26E978D4FDF_u64),
                        y: f64::from_bits(0x402BA8F5C28F5C29_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4054E26E978D4FDF_u64),
                        center_y: f64::from_bits(0x402BA8F5C28F5C29_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC02AE5604189374C_u64),
                        y: f64::from_bits(0x40333FBE76C8B439_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC02AE5604189374C_u64),
                        center_y: f64::from_bits(0x40333FBE76C8B439_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x404E6F5C28F5C28F_u64),
                        y: f64::from_bits(0xC04E874BC6A7EF9E_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404E6F5C28F5C28F_u64),
                        center_y: f64::from_bits(0xC04E874BC6A7EF9E_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 6), (2, 4), (4, 1), (1, 3), (2, 0), (0, 5)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_10",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_10", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC057715810624DD3_u64),
                        y: f64::from_bits(0x4045A78D4FDF3B64_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC057715810624DD3_u64),
                        center_y: f64::from_bits(0x4045A78D4FDF3B64_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0x4008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0x4008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC05485D2F1A9FBE7_u64),
                        y: f64::from_bits(0xC02472B020C49BA6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC05485D2F1A9FBE7_u64),
                        center_y: f64::from_bits(0xC02472B020C49BA6_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 6), (6, 3), (3, 1), (3, 4), (1, 5), (5, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_11",
                tags: &["fractional_coord", "multi_component", "named:rand_11", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4051CA8F5C28F5C3_u64),
                        y: f64::from_bits(0xC04FB126E978D4FE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4051CA8F5C28F5C3_u64),
                        center_y: f64::from_bits(0xC04FB126E978D4FE_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_12",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_12", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4041BC8B43958106_u64),
                        y: f64::from_bits(0xC000126E978D4FDF_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4041BC8B43958106_u64),
                        center_y: f64::from_bits(0xC000126E978D4FDF_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC04639374BC6A7F0_u64),
                        y: f64::from_bits(0x40369916872B020C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04639374BC6A7F0_u64),
                        center_y: f64::from_bits(0x40369916872B020C_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4023D916872B020C_u64),
                        y: f64::from_bits(0xC033FCAC083126E9_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4023D916872B020C_u64),
                        center_y: f64::from_bits(0xC033FCAC083126E9_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x40488810624DD2F2_u64),
                        y: f64::from_bits(0x4055DA1CAC083127_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40488810624DD2F2_u64),
                        center_y: f64::from_bits(0x4055DA1CAC083127_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC03AF2B020C49BA6_u64),
                        y: f64::from_bits(0x40506EC8B4395810_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC03AF2B020C49BA6_u64),
                        center_y: f64::from_bits(0x40506EC8B4395810_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 6), (2, 3), (3, 0), (0, 4), (0, 1), (6, 5)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_13",
                tags: &["multi_component", "named:rand_13", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_14",
                tags: &["multi_component", "named:rand_14", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 2), (2, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_15",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_15", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x40457E5604189375_u64),
                        y: f64::from_bits(0x404FB083126E978D_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x40457E5604189375_u64),
                        center_y: f64::from_bits(0x404FB083126E978D_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC040049BA5E353F8_u64),
                        y: f64::from_bits(0x405173C6A7EF9DB2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC040049BA5E353F8_u64),
                        center_y: f64::from_bits(0x405173C6A7EF9DB2_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 3), (0, 2), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_16",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_16", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC057ABE76C8B4396_u64),
                        y: f64::from_bits(0x4018FEF9DB22D0E5_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC057ABE76C8B4396_u64),
                        center_y: f64::from_bits(0x4018FEF9DB22D0E5_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0xC014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0xC014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 4), (4, 1), (1, 2), (3, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_17",
                tags: &["fractional_coord", "multi_component", "named:rand_17", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4049516872B020C5_u64),
                        y: f64::from_bits(0x40544F4BC6A7EF9E_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4049516872B020C5_u64),
                        center_y: f64::from_bits(0x40544F4BC6A7EF9E_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC04BEAC083126E98_u64),
                        y: f64::from_bits(0x401590624DD2F1AA_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04BEAC083126E98_u64),
                        center_y: f64::from_bits(0x401590624DD2F1AA_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x400A26E978D4FDF4_u64),
                        y: f64::from_bits(0x3FFA04189374BC6A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x400A26E978D4FDF4_u64),
                        center_y: f64::from_bits(0x3FFA04189374BC6A_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC04B74FDF3B645A2_u64),
                        y: f64::from_bits(0xC050DE45A1CAC083_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04B74FDF3B645A2_u64),
                        center_y: f64::from_bits(0xC050DE45A1CAC083_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (1, 3), (2, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_18",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_18", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0393AE147AE147B_u64),
                        y: f64::from_bits(0x404196C8B4395810_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0393AE147AE147B_u64),
                        center_y: f64::from_bits(0x404196C8B4395810_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0xC014000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0xC014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x40499083126E978D_u64),
                        y: f64::from_bits(0x4054F9374BC6A7F0_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40499083126E978D_u64),
                        center_y: f64::from_bits(0x4054F9374BC6A7F0_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4042C3F7CED91687_u64),
                        y: f64::from_bits(0xC056416872B020C5_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4042C3F7CED91687_u64),
                        center_y: f64::from_bits(0xC056416872B020C5_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 0), (2, 4), (0, 1), (4, 5), (1, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_19",
                tags: &["duplicate_identity", "fractional_coord", "multi_layer", "named:rand_19", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC03DF3F7CED91687_u64),
                        y: f64::from_bits(0xC055D3851EB851EC_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC03DF3F7CED91687_u64),
                        center_y: f64::from_bits(0xC055D3851EB851EC_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4030F95810624DD3_u64),
                        y: f64::from_bits(0x40486C49BA5E353F_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4030F95810624DD3_u64),
                        center_y: f64::from_bits(0x40486C49BA5E353F_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0xC014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0xC014000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_20",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_20", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x404239BA5E353F7D_u64),
                        y: f64::from_bits(0xC0560B3333333333_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404239BA5E353F7D_u64),
                        center_y: f64::from_bits(0xC0560B3333333333_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4047745A1CAC0831_u64),
                        y: f64::from_bits(0xC05270F5C28F5C29_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4047745A1CAC0831_u64),
                        center_y: f64::from_bits(0xC05270F5C28F5C29_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC057C21CAC083127_u64),
                        y: f64::from_bits(0x4053DF3B645A1CAC_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC057C21CAC083127_u64),
                        center_y: f64::from_bits(0x4053DF3B645A1CAC_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0xC0540DE353F7CED9_u64),
                        y: f64::from_bits(0xC05158E560418937_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0540DE353F7CED9_u64),
                        center_y: f64::from_bits(0xC05158E560418937_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (1, 5), (2, 3), (1, 4), (4, 0), (4, 7), (7, 6)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_21",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_21", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4049976C8B439581_u64),
                        y: f64::from_bits(0x40478624DD2F1AA0_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4049976C8B439581_u64),
                        center_y: f64::from_bits(0x40478624DD2F1AA0_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 2), (1, 4), (2, 0), (0, 3), (4, 5)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_22",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_22", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC046F5C28F5C28F6_u64),
                        y: f64::from_bits(0x403D87AE147AE148_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC046F5C28F5C28F6_u64),
                        center_y: f64::from_bits(0x403D87AE147AE148_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x404C08D4FDF3B646_u64),
                        y: f64::from_bits(0xC0317B22D0E56042_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404C08D4FDF3B646_u64),
                        center_y: f64::from_bits(0xC0317B22D0E56042_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC051FD70A3D70A3D_u64),
                        y: f64::from_bits(0x4032B1EB851EB852_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC051FD70A3D70A3D_u64),
                        center_y: f64::from_bits(0x4032B1EB851EB852_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                ],
                expected_root: 4,
                expected_edges: &[(4, 5), (5, 3), (4, 1), (3, 0), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_23",
                tags: &["duplicate_identity", "fractional_coord", "multi_component", "multi_layer", "named:rand_23", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4048BC8B43958106_u64),
                        y: f64::from_bits(0x40432A1CAC083127_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4048BC8B43958106_u64),
                        center_y: f64::from_bits(0x40432A1CAC083127_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0498147AE147AE1_u64),
                        y: f64::from_bits(0xC05862D0E5604189_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0498147AE147AE1_u64),
                        center_y: f64::from_bits(0xC05862D0E5604189_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x40456AC083126E98_u64),
                        y: f64::from_bits(0xC0559126E978D4FE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40456AC083126E98_u64),
                        center_y: f64::from_bits(0xC0559126E978D4FE_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x402E3BE76C8B4396_u64),
                        y: f64::from_bits(0xC0562E147AE147AE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x402E3BE76C8B4396_u64),
                        center_y: f64::from_bits(0xC0562E147AE147AE_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 3), (3, 1), (2, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_24",
                tags: &["fractional_coord", "named:rand_24", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC02050624DD2F1AA_u64),
                        y: f64::from_bits(0xC0545AD0E5604189_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC02050624DD2F1AA_u64),
                        center_y: f64::from_bits(0xC0545AD0E5604189_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_25",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_25", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC008000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC008000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4051A872B020C49C_u64),
                        y: f64::from_bits(0xC054A2B020C49BA6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4051A872B020C49C_u64),
                        center_y: f64::from_bits(0xC054A2B020C49BA6_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0xC014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0xC014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x40527C083126E979_u64),
                        y: f64::from_bits(0xC0585B851EB851EC_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40527C083126E979_u64),
                        center_y: f64::from_bits(0xC0585B851EB851EC_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC04535C28F5C28F6_u64),
                        y: f64::from_bits(0xC0571BF7CED91687_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04535C28F5C28F6_u64),
                        center_y: f64::from_bits(0xC0571BF7CED91687_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x405595C28F5C28F6_u64),
                        y: f64::from_bits(0x405701374BC6A7F0_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x405595C28F5C28F6_u64),
                        center_y: f64::from_bits(0x405701374BC6A7F0_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0xC042AEF9DB22D0E5_u64),
                        y: f64::from_bits(0xC0476C083126E979_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC042AEF9DB22D0E5_u64),
                        center_y: f64::from_bits(0xC0476C083126E979_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 3), (0, 7), (7, 5), (5, 4), (4, 2), (1, 6)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_26",
                tags: &["fractional_coord", "multi_component", "named:rand_26", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4048E7AE147AE148_u64),
                        y: f64::from_bits(0x404EF66666666666_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4048E7AE147AE148_u64),
                        center_y: f64::from_bits(0x404EF66666666666_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC040C020C49BA5E3_u64),
                        y: f64::from_bits(0x40455126E978D4FE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC040C020C49BA5E3_u64),
                        center_y: f64::from_bits(0x40455126E978D4FE_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC053D083126E978D_u64),
                        y: f64::from_bits(0xC04D2604189374BC_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC053D083126E978D_u64),
                        center_y: f64::from_bits(0xC04D2604189374BC_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_27",
                tags: &["multi_component", "named:rand_27", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x4008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x4008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC008000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC008000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 3), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_28",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_28", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x402490E560418937_u64),
                        y: f64::from_bits(0xC0464DD2F1A9FBE7_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x402490E560418937_u64),
                        center_y: f64::from_bits(0xC0464DD2F1A9FBE7_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_29",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_29", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x404D76A7EF9DB22D_u64),
                        y: f64::from_bits(0x404BF8D4FDF3B646_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404D76A7EF9DB22D_u64),
                        center_y: f64::from_bits(0x404BF8D4FDF3B646_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x403E2C8B43958106_u64),
                        y: f64::from_bits(0xC0579B53F7CED917_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403E2C8B43958106_u64),
                        center_y: f64::from_bits(0xC0579B53F7CED917_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4008000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4008000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 3), (3, 4), (3, 0), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_30",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_30", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC058B25E353F7CEE_u64),
                        y: f64::from_bits(0x401E96872B020C4A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC058B25E353F7CEE_u64),
                        center_y: f64::from_bits(0x401E96872B020C4A_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0528DC28F5C28F6_u64),
                        y: f64::from_bits(0x4043FB020C49BA5E_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0528DC28F5C28F6_u64),
                        center_y: f64::from_bits(0x4043FB020C49BA5E_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC05860D4FDF3B646_u64),
                        y: f64::from_bits(0xC02DF33333333333_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC05860D4FDF3B646_u64),
                        center_y: f64::from_bits(0xC02DF33333333333_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC0476604189374BC_u64),
                        y: f64::from_bits(0x405245C28F5C28F6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0476604189374BC_u64),
                        center_y: f64::from_bits(0x405245C28F5C28F6_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x402F0C49BA5E353F_u64),
                        y: f64::from_bits(0x40574EC8B4395810_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x402F0C49BA5E353F_u64),
                        center_y: f64::from_bits(0x40574EC8B4395810_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (0, 1), (1, 4), (4, 5), (5, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_31",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_31", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x404239374BC6A7F0_u64),
                        y: f64::from_bits(0x405195F3B645A1CB_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404239374BC6A7F0_u64),
                        center_y: f64::from_bits(0x405195F3B645A1CB_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC03C3E353F7CED91_u64),
                        y: f64::from_bits(0xC04BB0624DD2F1AA_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC03C3E353F7CED91_u64),
                        center_y: f64::from_bits(0xC04BB0624DD2F1AA_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC04430624DD2F1AA_u64),
                        y: f64::from_bits(0x3FEE76C8B4395810_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04430624DD2F1AA_u64),
                        center_y: f64::from_bits(0x3FEE76C8B4395810_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x403B570A3D70A3D7_u64),
                        y: f64::from_bits(0xC034EAC083126E98_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403B570A3D70A3D7_u64),
                        center_y: f64::from_bits(0xC034EAC083126E98_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 5), (5, 1), (1, 0), (0, 4), (4, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_32",
                tags: &["fractional_coord", "named:rand_32", "negative_coord", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC052F2B020C49BA6_u64),
                        y: f64::from_bits(0xC0554428F5C28F5C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC052F2B020C49BA6_u64),
                        center_y: f64::from_bits(0xC0554428F5C28F5C_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_33",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_33", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC04A43D70A3D70A4_u64),
                        y: f64::from_bits(0x400E26E978D4FDF4_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04A43D70A3D70A4_u64),
                        center_y: f64::from_bits(0x400E26E978D4FDF4_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC04303126E978D50_u64),
                        y: f64::from_bits(0xC04B6BC6A7EF9DB2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04303126E978D50_u64),
                        center_y: f64::from_bits(0xC04B6BC6A7EF9DB2_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC051647AE147AE14_u64),
                        y: f64::from_bits(0x4058023D70A3D70A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC051647AE147AE14_u64),
                        center_y: f64::from_bits(0x4058023D70A3D70A_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4043EF3B645A1CAC_u64),
                        y: f64::from_bits(0x404A40E560418937_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4043EF3B645A1CAC_u64),
                        center_y: f64::from_bits(0x404A40E560418937_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 3), (3, 7), (7, 6), (3, 1), (6, 5), (0, 2), (0, 4)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_34",
                tags: &["duplicate_identity", "fractional_coord", "multi_component", "multi_layer", "named:rand_34", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC0585A1CAC083127_u64),
                        y: f64::from_bits(0x40509A9FBE76C8B4_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC0585A1CAC083127_u64),
                        center_y: f64::from_bits(0x40509A9FBE76C8B4_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4056C083126E978D_u64),
                        y: f64::from_bits(0x4057E27EF9DB22D1_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4056C083126E978D_u64),
                        center_y: f64::from_bits(0x4057E27EF9DB22D1_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x40388DD2F1A9FBE7_u64),
                        y: f64::from_bits(0xC050E7CED916872B_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40388DD2F1A9FBE7_u64),
                        center_y: f64::from_bits(0xC050E7CED916872B_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_35",
                tags: &["multi_component", "multi_layer", "named:rand_35", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_36",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_36", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC018000000000000_u64),
                        y: f64::from_bits(0xC010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC018000000000000_u64),
                        center_y: f64::from_bits(0xC010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4051650E56041893_u64),
                        y: f64::from_bits(0x405612C083126E98_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4051650E56041893_u64),
                        center_y: f64::from_bits(0x405612C083126E98_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC045B66666666666_u64),
                        y: f64::from_bits(0x4051E395810624DD_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC045B66666666666_u64),
                        center_y: f64::from_bits(0x4051E395810624DD_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xBFF5B645A1CAC083_u64),
                        y: f64::from_bits(0xC0481083126E978D_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xBFF5B645A1CAC083_u64),
                        center_y: f64::from_bits(0xC0481083126E978D_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 0), (0, 1), (1, 4), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_37",
                tags: &["duplicate_identity", "fractional_coord", "multi_component", "named:rand_37", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC0583322D0E56042_u64),
                        y: f64::from_bits(0x403F72B020C49BA6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0583322D0E56042_u64),
                        center_y: f64::from_bits(0x403F72B020C49BA6_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC056FE76C8B43958_u64),
                        y: f64::from_bits(0x4048C9374BC6A7F0_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC056FE76C8B43958_u64),
                        center_y: f64::from_bits(0x4048C9374BC6A7F0_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0), (0, 2), (2, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_38",
                tags: &["named:rand_38", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_39",
                tags: &["multi_component", "multi_layer", "named:rand_39", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC018000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC018000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_40",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_40", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0538A8F5C28F5C3_u64),
                        y: f64::from_bits(0x40571570A3D70A3D_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0538A8F5C28F5C3_u64),
                        center_y: f64::from_bits(0x40571570A3D70A3D_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_41",
                tags: &["fractional_coord", "multi_component", "named:rand_41", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC0530BB645A1CAC1_u64),
                        y: f64::from_bits(0xC04824BC6A7EF9DB_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0530BB645A1CAC1_u64),
                        center_y: f64::from_bits(0xC04824BC6A7EF9DB_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x40336A7EF9DB22D1_u64),
                        y: f64::from_bits(0xC03012B020C49BA6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40336A7EF9DB22D1_u64),
                        center_y: f64::from_bits(0xC03012B020C49BA6_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x404A6E353F7CED91_u64),
                        y: f64::from_bits(0xC029F6C8B4395810_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404A6E353F7CED91_u64),
                        center_y: f64::from_bits(0xC029F6C8B4395810_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 1), (1, 3), (1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_42",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_42", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0xC022000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0xC022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x40478D916872B021_u64),
                        y: f64::from_bits(0x402F5810624DD2F2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40478D916872B021_u64),
                        center_y: f64::from_bits(0x402F5810624DD2F2_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 3), (1, 0), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_43",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_43", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC05659EB851EB852_u64),
                        y: f64::from_bits(0x403316872B020C4A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC05659EB851EB852_u64),
                        center_y: f64::from_bits(0x403316872B020C4A_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x402A6978D4FDF3B6_u64),
                        y: f64::from_bits(0xC01B126E978D4FDF_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x402A6978D4FDF3B6_u64),
                        center_y: f64::from_bits(0xC01B126E978D4FDF_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 1), (3, 2), (3, 4), (4, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_44",
                tags: &["named:rand_44", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4008000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4008000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_45",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_45", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC018E45A1CAC0831_u64),
                        y: f64::from_bits(0xC0116F9DB22D0E56_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC018E45A1CAC0831_u64),
                        center_y: f64::from_bits(0xC0116F9DB22D0E56_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC03DEC083126E979_u64),
                        y: f64::from_bits(0xC042E916872B020C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC03DEC083126E979_u64),
                        center_y: f64::from_bits(0xC042E916872B020C_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC0533F4BC6A7EF9E_u64),
                        y: f64::from_bits(0x4054DC083126E979_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0533F4BC6A7EF9E_u64),
                        center_y: f64::from_bits(0x4054DC083126E979_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC045216872B020C5_u64),
                        y: f64::from_bits(0x4042E4DD2F1A9FBE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC045216872B020C5_u64),
                        center_y: f64::from_bits(0x4042E4DD2F1A9FBE_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC057F072B020C49C_u64),
                        y: f64::from_bits(0xC03834FDF3B645A2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC057F072B020C49C_u64),
                        center_y: f64::from_bits(0xC03834FDF3B645A2_u64),
                    },
                ],
                expected_root: 4,
                expected_edges: &[(4, 5), (5, 1), (1, 0), (1, 2), (2, 6), (4, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_46",
                tags: &["fractional_coord", "multi_component", "named:rand_46", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x40437A9FBE76C8B4_u64),
                        y: f64::from_bits(0x404D204189374BC7_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40437A9FBE76C8B4_u64),
                        center_y: f64::from_bits(0x404D204189374BC7_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 2), (2, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_47",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_47", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0x4008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0x4008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC01748B439581062_u64),
                        y: f64::from_bits(0xC03657CED916872B_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC01748B439581062_u64),
                        center_y: f64::from_bits(0xC03657CED916872B_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x40555AF1A9FBE76D_u64),
                        y: f64::from_bits(0x40319126E978D4FE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40555AF1A9FBE76D_u64),
                        center_y: f64::from_bits(0x40319126E978D4FE_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 1), (0, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_48",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_48", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4050A96872B020C5_u64),
                        y: f64::from_bits(0x4051B4189374BC6A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4050A96872B020C5_u64),
                        center_y: f64::from_bits(0x4051B4189374BC6A_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC054696872B020C5_u64),
                        y: f64::from_bits(0x4037578D4FDF3B64_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC054696872B020C5_u64),
                        center_y: f64::from_bits(0x4037578D4FDF3B64_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC057B189374BC6A8_u64),
                        y: f64::from_bits(0xC03214FDF3B645A2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC057B189374BC6A8_u64),
                        center_y: f64::from_bits(0xC03214FDF3B645A2_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 3), (3, 5), (3, 4), (4, 2), (5, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_49",
                tags: &["multi_layer", "named:rand_49", "negative_coord", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC008000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC008000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_50",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_50", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x401D04189374BC6A_u64),
                        y: f64::from_bits(0x403A589374BC6A7F_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401D04189374BC6A_u64),
                        center_y: f64::from_bits(0x403A589374BC6A7F_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x403E051EB851EB85_u64),
                        y: f64::from_bits(0x40488E5604189375_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x403E051EB851EB85_u64),
                        center_y: f64::from_bits(0x40488E5604189375_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4054921CAC083127_u64),
                        y: f64::from_bits(0xC03B795810624DD3_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4054921CAC083127_u64),
                        center_y: f64::from_bits(0xC03B795810624DD3_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x403B2ED916872B02_u64),
                        y: f64::from_bits(0x3FB70A3D70A3D70A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403B2ED916872B02_u64),
                        center_y: f64::from_bits(0x3FB70A3D70A3D70A_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC050AA2D0E560419_u64),
                        y: f64::from_bits(0x40530B126E978D50_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC050AA2D0E560419_u64),
                        center_y: f64::from_bits(0x40530B126E978D50_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 4), (0, 1), (4, 3), (0, 5)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_51",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_51", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x403C1CAC083126E9_u64),
                        y: f64::from_bits(0x40407D2F1A9FBE77_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403C1CAC083126E9_u64),
                        center_y: f64::from_bits(0x40407D2F1A9FBE77_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x40530CCCCCCCCCCD_u64),
                        y: f64::from_bits(0x40430C28F5C28F5C_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40530CCCCCCCCCCD_u64),
                        center_y: f64::from_bits(0x40430C28F5C28F5C_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 3), (3, 0), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_52",
                tags: &["fractional_coord", "multi_component", "named:rand_52", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC04556E978D4FDF4_u64),
                        y: f64::from_bits(0xC05206A7EF9DB22D_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04556E978D4FDF4_u64),
                        center_y: f64::from_bits(0xC05206A7EF9DB22D_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_53",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_53", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC05554189374BC6A_u64),
                        y: f64::from_bits(0x40456D4FDF3B645A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC05554189374BC6A_u64),
                        center_y: f64::from_bits(0x40456D4FDF3B645A_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_54",
                tags: &["multi_component", "multi_layer", "named:rand_54", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0xC010000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0xC010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0), (0, 2), (2, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_55",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_55", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC04793D70A3D70A4_u64),
                        y: f64::from_bits(0xC058F072B020C49C_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC04793D70A3D70A4_u64),
                        center_y: f64::from_bits(0xC058F072B020C49C_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0xC014000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0xC014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4053B78D4FDF3B64_u64),
                        y: f64::from_bits(0x4052866666666666_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4053B78D4FDF3B64_u64),
                        center_y: f64::from_bits(0x4052866666666666_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_56",
                tags: &["fractional_coord", "named:rand_56", "negative_coord", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC054FBC6A7EF9DB2_u64),
                        y: f64::from_bits(0xC03BE5A1CAC08312_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC054FBC6A7EF9DB2_u64),
                        center_y: f64::from_bits(0xC03BE5A1CAC08312_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_57",
                tags: &["fractional_coord", "multi_component", "named:rand_57", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC03CF0E560418937_u64),
                        y: f64::from_bits(0x4045C20C49BA5E35_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC03CF0E560418937_u64),
                        center_y: f64::from_bits(0x4045C20C49BA5E35_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC04481CAC083126F_u64),
                        y: f64::from_bits(0xC040E020C49BA5E3_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04481CAC083126F_u64),
                        center_y: f64::from_bits(0xC040E020C49BA5E3_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4008000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4008000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC058A33333333333_u64),
                        y: f64::from_bits(0xC03E9126E978D4FE_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC058A33333333333_u64),
                        center_y: f64::from_bits(0xC03E9126E978D4FE_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 1), (1, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_58",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_58"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4055279DB22D0E56_u64),
                        y: f64::from_bits(0x4043076C8B439581_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4055279DB22D0E56_u64),
                        center_y: f64::from_bits(0x4043076C8B439581_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 1), (1, 0), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_59",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_59", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC050634395810625_u64),
                        y: f64::from_bits(0xC03F47EF9DB22D0E_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC050634395810625_u64),
                        center_y: f64::from_bits(0xC03F47EF9DB22D0E_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x40560B851EB851EC_u64),
                        y: f64::from_bits(0xC0503E24DD2F1AA0_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40560B851EB851EC_u64),
                        center_y: f64::from_bits(0xC0503E24DD2F1AA0_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC024000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC024000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC018000000000000_u64),
                        y: f64::from_bits(0x4024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC018000000000000_u64),
                        center_y: f64::from_bits(0x4024000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 3), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_60",
                tags: &["fractional_coord", "multi_component", "named:rand_60", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4008000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4008000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x40530449BA5E353F_u64),
                        y: f64::from_bits(0x402C3645A1CAC083_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40530449BA5E353F_u64),
                        center_y: f64::from_bits(0x402C3645A1CAC083_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC0542010624DD2F2_u64),
                        y: f64::from_bits(0xC0574A0C49BA5E35_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0542010624DD2F2_u64),
                        center_y: f64::from_bits(0xC0574A0C49BA5E35_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC04CB8B439581062_u64),
                        y: f64::from_bits(0xC03C845A1CAC0831_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04CB8B439581062_u64),
                        center_y: f64::from_bits(0xC03C845A1CAC0831_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 0), (0, 3), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_61",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "named:rand_61", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x405800D4FDF3B646_u64),
                        y: f64::from_bits(0xC049372B020C49BA_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x405800D4FDF3B646_u64),
                        center_y: f64::from_bits(0xC049372B020C49BA_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4058CD4FDF3B645A_u64),
                        y: f64::from_bits(0x4048C0A3D70A3D71_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4058CD4FDF3B645A_u64),
                        center_y: f64::from_bits(0x4048C0A3D70A3D71_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4051E449BA5E353F_u64),
                        y: f64::from_bits(0x40518147AE147AE1_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4051E449BA5E353F_u64),
                        center_y: f64::from_bits(0x40518147AE147AE1_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x401C000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401C000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                ],
                expected_root: 4,
                expected_edges: &[(4, 1), (4, 3), (3, 2), (2, 0)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_62",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_62", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4008000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4008000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC05158E560418937_u64),
                        y: f64::from_bits(0xC0462189374BC6A8_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC05158E560418937_u64),
                        center_y: f64::from_bits(0xC0462189374BC6A8_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4039FC6A7EF9DB23_u64),
                        y: f64::from_bits(0x3FA374BC6A7EF9DB_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4039FC6A7EF9DB23_u64),
                        center_y: f64::from_bits(0x3FA374BC6A7EF9DB_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 5), (0, 1), (1, 2), (1, 4), (2, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_63",
                tags: &["fractional_coord", "multi_component", "named:rand_63", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC047EDF3B645A1CB_u64),
                        y: f64::from_bits(0x404689BA5E353F7D_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC047EDF3B645A1CB_u64),
                        center_y: f64::from_bits(0x404689BA5E353F7D_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC04A34DD2F1A9FBE_u64),
                        y: f64::from_bits(0xC045A810624DD2F2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC04A34DD2F1A9FBE_u64),
                        center_y: f64::from_bits(0xC045A810624DD2F2_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xBFF2978D4FDF3B64_u64),
                        y: f64::from_bits(0xC057E189374BC6A8_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF2978D4FDF3B64_u64),
                        center_y: f64::from_bits(0xC057E189374BC6A8_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 3), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_64",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_64", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0xC010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0xC010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC008000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC008000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x405338A3D70A3D71_u64),
                        y: f64::from_bits(0x4051589374BC6A7F_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x405338A3D70A3D71_u64),
                        center_y: f64::from_bits(0x4051589374BC6A7F_u64),
                    },
                ],
                expected_root: 2,
                expected_edges: &[(2, 0), (0, 3), (3, 1), (2, 4)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_65",
                tags: &["fractional_coord", "named:rand_65", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4057923D70A3D70A_u64),
                        y: f64::from_bits(0x404354395810624E_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4057923D70A3D70A_u64),
                        center_y: f64::from_bits(0x404354395810624E_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (0, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_66",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "named:rand_66", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x404A6BA5E353F7CF_u64),
                        y: f64::from_bits(0x403A90A3D70A3D71_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404A6BA5E353F7CF_u64),
                        center_y: f64::from_bits(0x403A90A3D70A3D71_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC02695810624DD2F_u64),
                        y: f64::from_bits(0x40455604189374BC_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC02695810624DD2F_u64),
                        center_y: f64::from_bits(0x40455604189374BC_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC0566810624DD2F2_u64),
                        y: f64::from_bits(0xC0494EF9DB22D0E5_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0566810624DD2F2_u64),
                        center_y: f64::from_bits(0xC0494EF9DB22D0E5_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0xC018000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC018000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 2), (2, 7), (7, 6), (6, 4), (4, 5), (6, 1), (4, 3)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_67",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "named:rand_67", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0xC022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0xC022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0x4008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0x4008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0xC01C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0xC01C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4014000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4014000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x403C600000000000_u64),
                        y: f64::from_bits(0xC03D12B020C49BA6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403C600000000000_u64),
                        center_y: f64::from_bits(0xC03D12B020C49BA6_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x0000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x0000000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 4), (1, 6), (6, 0), (0, 3), (3, 2), (0, 5)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_68",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_68", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x40587BE76C8B4396_u64),
                        y: f64::from_bits(0xC02C27EF9DB22D0E_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x40587BE76C8B4396_u64),
                        center_y: f64::from_bits(0xC02C27EF9DB22D0E_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0522F9DB22D0E56_u64),
                        y: f64::from_bits(0xBFD999999999999A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0522F9DB22D0E56_u64),
                        center_y: f64::from_bits(0xBFD999999999999A_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x40530BC6A7EF9DB2_u64),
                        y: f64::from_bits(0xC057FDC28F5C28F6_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x40530BC6A7EF9DB2_u64),
                        center_y: f64::from_bits(0xC057FDC28F5C28F6_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC0514989374BC6A8_u64),
                        y: f64::from_bits(0xC0447374BC6A7EFA_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0514989374BC6A8_u64),
                        center_y: f64::from_bits(0xC0447374BC6A7EFA_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC03D049BA5E353F8_u64),
                        y: f64::from_bits(0xC04217CED916872B_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC03D049BA5E353F8_u64),
                        center_y: f64::from_bits(0xC04217CED916872B_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0xC052B9CAC083126F_u64),
                        y: f64::from_bits(0x4057CA1CAC083127_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC052B9CAC083126F_u64),
                        center_y: f64::from_bits(0x4057CA1CAC083127_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 0), (0, 5), (5, 2), (5, 6), (6, 4), (4, 1), (1, 7)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_69",
                tags: &["fractional_coord", "named:rand_69", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x403F2189374BC6A8_u64),
                        y: f64::from_bits(0x405323851EB851EC_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x403F2189374BC6A8_u64),
                        center_y: f64::from_bits(0x405323851EB851EC_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_70",
                tags: &["fractional_coord", "named:rand_70", "negative_coord", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC051D7EF9DB22D0E_u64),
                        y: f64::from_bits(0xC056F0F5C28F5C29_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC051D7EF9DB22D0E_u64),
                        center_y: f64::from_bits(0xC056F0F5C28F5C29_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_71",
                tags: &["fractional_coord", "multi_layer", "named:rand_71", "negative_coord", "single_pad"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC0168624DD2F1AA0_u64),
                        y: f64::from_bits(0x4052CF4BC6A7EF9E_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC0168624DD2F1AA0_u64),
                        center_y: f64::from_bits(0x4052CF4BC6A7EF9E_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_72",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "named:rand_72", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x404345A1CAC08312_u64),
                        y: f64::from_bits(0xC03AE5E353F7CED9_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404345A1CAC08312_u64),
                        center_y: f64::from_bits(0xC03AE5E353F7CED9_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC0540A0C49BA5E35_u64),
                        y: f64::from_bits(0xBFF94FDF3B645A1D_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC0540A0C49BA5E35_u64),
                        center_y: f64::from_bits(0xBFF94FDF3B645A1D_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x3FFE9FBE76C8B439_u64),
                        y: f64::from_bits(0xC058190624DD2F1B_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FFE9FBE76C8B439_u64),
                        center_y: f64::from_bits(0xC058190624DD2F1B_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x4000000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4000000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0x4014000000000000_u64),
                        y: f64::from_bits(0x401C000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4014000000000000_u64),
                        center_y: f64::from_bits(0x401C000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0x404350A3D70A3D71_u64),
                        y: f64::from_bits(0x4040EA3D70A3D70A_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404350A3D70A3D71_u64),
                        center_y: f64::from_bits(0x4040EA3D70A3D70A_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 5), (5, 4), (4, 3), (3, 6), (6, 7), (4, 1), (5, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_73",
                tags: &["fractional_coord", "multi_component", "named:rand_73", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC026EF9DB22D0E56_u64),
                        y: f64::from_bits(0x404B8FDF3B645A1D_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC026EF9DB22D0E56_u64),
                        center_y: f64::from_bits(0x404B8FDF3B645A1D_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0x4010000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0x4010000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC01C000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC01C000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 3), (3, 2), (2, 1)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_74",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_74", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC04AC4395810624E_u64),
                        y: f64::from_bits(0xC030EB020C49BA5E_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC04AC4395810624E_u64),
                        center_y: f64::from_bits(0xC030EB020C49BA5E_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0xBFF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0xBFF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4056C6E978D4FDF4_u64),
                        y: f64::from_bits(0xC043E5E353F7CED9_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4056C6E978D4FDF4_u64),
                        center_y: f64::from_bits(0xC043E5E353F7CED9_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0x3FF0000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0x3FF0000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x0000000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x0000000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 5), (5, 4), (5, 1), (1, 3), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_75",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_75", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4032E66666666666_u64),
                        y: f64::from_bits(0x4046A72B020C49BA_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4032E66666666666_u64),
                        center_y: f64::from_bits(0x4046A72B020C49BA_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xBFF0000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xBFF0000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC05735916872B021_u64),
                        y: f64::from_bits(0x405821A9FBE76C8B_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC05735916872B021_u64),
                        center_y: f64::from_bits(0x405821A9FBE76C8B_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0xC055C3C6A7EF9DB2_u64),
                        y: f64::from_bits(0x4052E1BA5E353F7D_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC055C3C6A7EF9DB2_u64),
                        center_y: f64::from_bits(0x4052E1BA5E353F7D_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0x3FF0000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FF0000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x404289FBE76C8B44_u64),
                        y: f64::from_bits(0xC0218DD2F1A9FBE7_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x404289FBE76C8B44_u64),
                        center_y: f64::from_bits(0xC0218DD2F1A9FBE7_u64),
                    },
                ],
                expected_root: 3,
                expected_edges: &[(3, 2), (3, 0), (0, 1), (1, 4), (4, 5)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_76",
                tags: &["fractional_coord", "multi_component", "named:rand_76", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4056D80000000000_u64),
                        y: f64::from_bits(0xC0216B020C49BA5E_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4056D80000000000_u64),
                        center_y: f64::from_bits(0xC0216B020C49BA5E_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x3FFBDF3B645A1CAC_u64),
                        y: f64::from_bits(0xC02094FDF3B645A2_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x3FFBDF3B645A1CAC_u64),
                        center_y: f64::from_bits(0xC02094FDF3B645A2_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC055B5E353F7CED9_u64),
                        y: f64::from_bits(0x403A4C083126E979_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC055B5E353F7CED9_u64),
                        center_y: f64::from_bits(0x403A4C083126E979_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0x4010000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4010000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 1), (1, 3), (3, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_77",
                tags: &["duplicate_identity", "fractional_coord", "large_pad_count", "multi_component", "named:rand_77", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "R1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0xC000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0xC000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x401B800000000000_u64),
                        y: f64::from_bits(0xC03BEA7EF9DB22D1_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x401B800000000000_u64),
                        center_y: f64::from_bits(0xC03BEA7EF9DB22D1_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4020000000000000_u64),
                        y: f64::from_bits(0x4018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4020000000000000_u64),
                        center_y: f64::from_bits(0x4018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC014000000000000_u64),
                        y: f64::from_bits(0xC024000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC014000000000000_u64),
                        center_y: f64::from_bits(0xC024000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0xC000000000000000_u64),
                        y: f64::from_bits(0xC008000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC000000000000000_u64),
                        center_y: f64::from_bits(0xC008000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0xC010000000000000_u64),
                        y: f64::from_bits(0xC022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC010000000000000_u64),
                        center_y: f64::from_bits(0xC022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0xC043FA9FBE76C8B4_u64),
                        y: f64::from_bits(0x4049FE353F7CED91_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC043FA9FBE76C8B4_u64),
                        center_y: f64::from_bits(0x4049FE353F7CED91_u64),
                    },
                ],
                expected_root: 6,
                expected_edges: &[(6, 4), (6, 3), (3, 5), (5, 0), (0, 2), (0, 1), (3, 7)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_78",
                tags: &["fractional_coord", "large_pad_count", "multi_component", "multi_layer", "named:rand_78", "negative_coord", "tied_distance"],
                pads: &[
                    FrozenPad {
                        component_ref: "J1",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0x4024000000000000_u64),
                        y: f64::from_bits(0xC020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4024000000000000_u64),
                        center_y: f64::from_bits(0xC020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x404135C28F5C28F6_u64),
                        y: f64::from_bits(0x402FFF7CED916873_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x404135C28F5C28F6_u64),
                        center_y: f64::from_bits(0x402FFF7CED916873_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4054054FDF3B645A_u64),
                        y: f64::from_bits(0xC052E6978D4FDF3B_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x4054054FDF3B645A_u64),
                        center_y: f64::from_bits(0xC052E6978D4FDF3B_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "3",
                        net: "NET",
                        x: f64::from_bits(0xC008000000000000_u64),
                        y: f64::from_bits(0xC018000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC008000000000000_u64),
                        center_y: f64::from_bits(0xC018000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "4",
                        net: "NET",
                        x: f64::from_bits(0xC020000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC020000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "5",
                        net: "NET",
                        x: f64::from_bits(0x402774395810624E_u64),
                        y: f64::from_bits(0x40532D916872B021_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x402774395810624E_u64),
                        center_y: f64::from_bits(0x40532D916872B021_u64),
                    },
                    FrozenPad {
                        component_ref: "R1",
                        pad: "6",
                        net: "NET",
                        x: f64::from_bits(0xC022000000000000_u64),
                        y: f64::from_bits(0x4020000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0xC022000000000000_u64),
                        center_y: f64::from_bits(0x4020000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U1",
                        pad: "7",
                        net: "NET",
                        x: f64::from_bits(0x405666C8B4395810_u64),
                        y: f64::from_bits(0xC041C51EB851EB85_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0x405666C8B4395810_u64),
                        center_y: f64::from_bits(0xC041C51EB851EB85_u64),
                    },
                ],
                expected_root: 0,
                expected_edges: &[(0, 3), (3, 4), (4, 6), (0, 1), (1, 5), (1, 7), (7, 2)],
                expected_error: None,
            },
            FrozenTerminalTreeCase {
                name: "rand_79",
                tags: &["fractional_coord", "multi_component", "multi_layer", "named:rand_79", "negative_coord"],
                pads: &[
                    FrozenPad {
                        component_ref: "U2",
                        pad: "0",
                        net: "NET",
                        x: f64::from_bits(0xC052E34395810625_u64),
                        y: f64::from_bits(0x4057C75C28F5C28F_u64),
                        layers: &[0, 31],
                        center_x: f64::from_bits(0xC052E34395810625_u64),
                        center_y: f64::from_bits(0x4057C75C28F5C28F_u64),
                    },
                    FrozenPad {
                        component_ref: "J1",
                        pad: "1",
                        net: "NET",
                        x: f64::from_bits(0x4018000000000000_u64),
                        y: f64::from_bits(0x4000000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4018000000000000_u64),
                        center_y: f64::from_bits(0x4000000000000000_u64),
                    },
                    FrozenPad {
                        component_ref: "U2",
                        pad: "2",
                        net: "NET",
                        x: f64::from_bits(0x4022000000000000_u64),
                        y: f64::from_bits(0x4022000000000000_u64),
                        layers: &[0],
                        center_x: f64::from_bits(0x4022000000000000_u64),
                        center_y: f64::from_bits(0x4022000000000000_u64),
                    },
                ],
                expected_root: 1,
                expected_edges: &[(1, 2), (2, 0)],
                expected_error: None,
            },
        ];

        fn frozen_pad_identity(p: &FrozenPad) -> PadIdentity {
            PadIdentity {
                component_ref: p.component_ref.to_string(),
                pad: p.pad.to_string(),
                net: p.net.to_string(),
                x: p.x,
                y: p.y,
                layers: p.layers.to_vec(),
            }
        }

        #[cfg_attr(test, test)]
        fn frozen_terminal_tree_matches_golden_corpus() {
            for case in FROZEN_TERMINAL_TREE_GOLDEN {
                let pads: Vec<TreePad> = case.pads.iter()
                    .map(|p| TreePad {
                        identity: frozen_pad_identity(p),
                        center: (p.center_x, p.center_y),
                    })
                    .collect();
                match plan_terminal_tree(&pads) {
                    Err(msg) => assert_eq!(
                        Some(msg.as_str()),
                        case.expected_error,
                        "case {}: error mismatch",
                        case.name
                    ),
                    Ok(plan) => {
                        assert!(
                            case.expected_error.is_none(),
                            "case {}: expected error, got a plan",
                            case.name
                        );
                        let idx_of = |id: &PadIdentity| -> usize {
                            case.pads
                                .iter()
                                .position(|p| {
                                    let fid = frozen_pad_identity(p);
                                    fid.component_ref == id.component_ref
                                        && fid.pad == id.pad
                                        && fid.net == id.net
                                        && fid.x == id.x
                                        && fid.y == id.y
                                        && fid.layers == id.layers
                                })
                                .unwrap_or_else(|| {
                                    panic!(
                                        "case {}: output identity not among inputs",
                                        case.name
                                    )
                                })
                        };
                        assert_eq!(idx_of(&plan.root), case.expected_root, "case {} root", case.name);
                        let got_edges: Vec<(usize, usize)> = plan
                            .edges
                            .iter()
                            .map(|(s, t)| (idx_of(s), idx_of(t)))
                            .collect();
                        assert_eq!(&got_edges[..], case.expected_edges, "case {} edges", case.name);
                    }
                }
            }
        }

        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were
        /// ever hand-edited down to something trivially satisfiable.
        #[cfg_attr(test, test)]
        fn frozen_terminal_tree_corpus_is_non_vacuous() {
            let n = FROZEN_TERMINAL_TREE_GOLDEN.len() as u32;
            let count = |tag: &str| FROZEN_TERMINAL_TREE_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(count("multi_component") * 100 >= n * 15, "multi_component: only {}/{} (need >= 15%) -- cross-component identities must be exercised (root selection)", count("multi_component"), n);
            assert!(count("tied_distance") >= 10, "tied_distance: only {}/{} (need >= 10) -- the identity tie-break must be exercised (the hash-order trap)", count("tied_distance"), n);
            assert!(count("negative_coord") >= 10, "negative_coord: only {}/{} (need >= 10) -- negative coordinates must be exercised", count("negative_coord"), n);
            assert!(count("fractional_coord") >= 10, "fractional_coord: only {}/{} (need >= 10) -- fractional coordinates must be exercised", count("fractional_coord"), n);
            assert!(count("duplicate_identity") >= 3, "duplicate_identity: only {}/{} (need >= 3) -- the dedup-by-identity path must be exercised", count("duplicate_identity"), n);
            assert!(count("multi_layer") >= 3, "multi_layer: only {}/{} (need >= 3) -- non-default layer tuples in the identity key must be exercised", count("multi_layer"), n);
            assert!(count("empty") >= 1, "empty: only {}/{} (need >= 1) -- the empty-input ValueError branch must be exercised", count("empty"), n);
            assert!(count("single_pad") >= 2, "single_pad: only {}/{} (need >= 2) -- the zero-edge single-terminal plan must be exercised", count("single_pad"), n);
        }

        // --- BEGIN generated by scripts/gen_wasm_test_registry.py: frozen_terminal_tree_tests ---
        /// Every `#[test]` in this module, as a callable the `wasm32`
        /// entry point can invoke by index.  Generated because these
        /// functions are private to this module and unreachable from
        /// anywhere a registry could otherwise live.
        pub const WASM_TESTS: &[(&str, fn())] = &[
            ("terminal_planning::frozen_terminal_tree_tests::frozen_terminal_tree_matches_golden_corpus", frozen_terminal_tree_matches_golden_corpus),
            ("terminal_planning::frozen_terminal_tree_tests::frozen_terminal_tree_corpus_is_non_vacuous", frozen_terminal_tree_corpus_is_non_vacuous),
        ];
        // --- END generated by scripts/gen_wasm_test_registry.py: frozen_terminal_tree_tests ---
    }
// --- END generated by scripts/gen_oracle_freeze.py: terminal_tree ---

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn pad(component_ref: &str, index: i64, x: f64, y: f64) -> TreePad {
        TreePad {
            identity: PadIdentity {
                component_ref: component_ref.to_string(),
                pad: index.to_string(),
                net: "NET".to_string(),
                x,
                y,
                layers: vec![0],
            },
            center: (x, y),
        }
    }

    #[cfg_attr(test, test)]
    fn plan_terminal_tree_roots_at_lexicographically_smallest_identity() {
        let pads = vec![pad("U1", 2, 10.0, 0.0), pad("U1", 1, 0.0, 0.0), pad("U1", 3, 0.0, 10.0)];
        let plan = match plan_terminal_tree(&pads) {
            Ok(plan) => plan,
            Err(e) => panic!("expected a plan for non-empty pads, got Err({e})"),
        };
        assert_eq!(plan.root.pad, "1");
        assert_eq!(
            plan.edges
                .iter()
                .map(|(s, t)| (s.pad.clone(), t.pad.clone()))
                .collect::<Vec<_>>(),
            vec![("1".to_string(), "2".to_string()), ("1".to_string(), "3".to_string())]
        );
    }

    #[cfg_attr(test, test)]
    fn plan_terminal_tree_rejects_empty_input() {
        assert!(plan_terminal_tree(&[]).is_err());
    }

    #[cfg_attr(test, test)]
    fn extract_net_terminals_skips_missing_component_and_pin() {
        let comp = ComponentRow {
            component_ref: "U1".to_string(),
            initial_position: Some((0.0, 0.0)),
            initial_rotation_rad: 0.0,
            initial_side: None,
            pins: vec![PinRow {
                name: "1".to_string(),
                number: "1".to_string(),
                position: (0.0, 0.0),
                is_pth: false,
                layer: Some("F.Cu".to_string()),
            }],
        };
        let net_pins = vec![
            ("U1".to_string(), "1".to_string()),
            ("GHOST".to_string(), "1".to_string()),
            ("U1".to_string(), "99".to_string()),
        ];
        let out = extract_net_terminals("NET", &net_pins, &[comp], &[]);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].component_ref, "U1");
    }

    #[cfg_attr(test, test)]
    fn extract_net_terminals_mirrors_bottom_side_before_rotating() {
        let comp = ComponentRow {
            component_ref: "U1".to_string(),
            initial_position: Some((5.0, 5.0)),
            initial_rotation_rad: 0.0,
            initial_side: Some(1),
            pins: vec![PinRow {
                name: "1".to_string(),
                number: "1".to_string(),
                position: (2.0, 0.0),
                is_pth: false,
                layer: Some("F.Cu".to_string()),
            }],
        };
        let out = extract_net_terminals("NET", &[("U1".to_string(), "1".to_string())], &[comp], &[]);
        // side=1 mirrors px -> -2.0 before rotation (theta=0), so world x
        // is 5.0 + (-2.0) = 3.0, not 5.0 + 2.0 = 7.0.
        assert_eq!(out[0].x, 3.0);
        assert_eq!(out[0].y, 5.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("terminal_planning::tests::plan_terminal_tree_roots_at_lexicographically_smallest_identity", plan_terminal_tree_roots_at_lexicographically_smallest_identity),
        ("terminal_planning::tests::plan_terminal_tree_rejects_empty_input", plan_terminal_tree_rejects_empty_input),
        ("terminal_planning::tests::extract_net_terminals_skips_missing_component_and_pin", extract_net_terminals_skips_missing_component_and_pin),
        ("terminal_planning::tests::extract_net_terminals_mirrors_bottom_side_before_rotating", extract_net_terminals_mirrors_bottom_side_before_rotating),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
