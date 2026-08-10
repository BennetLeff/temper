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
//! * `Component.initial_rotation` is typed `int | None`
//!   (`core/netlist.py`'s installed dataclass contract) -- the
//!   float-radians branch of `_normalize_rotation` is unreachable through
//!   the real object model, so [`normalize_rotation`] takes `Option<i64>`,
//!   exactly like `net_ordering.rs`'s `pin_world_position` for the
//!   identical reason.
//! * `sorted(terminals, key=lambda t: t.identity)` in
//!   `extract_net_terminals` is CPython's stable timsort. This module uses
//!   `Vec::sort_by`, which the Rust standard library also guarantees
//!   stable -- `sort_unstable_by` would diverge on ties (duplicate
//!   `(component_ref, pad)` entries in `net_pins` produce a genuine tie on
//!   the full `PadIdentity` key, and Python's `sorted()` preserves their
//!   relative input order in that case).

use std::cmp::Ordering;
use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
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
    initial_rotation: Option<i64>,
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

/// `core/pin_geometry._normalize_rotation`'s int-index branch. `None` is
/// `0.0` rad. See this module's docstring: the float-radians branch is
/// unreachable through `Component.initial_rotation`'s real `int | None`
/// contract, so it is not modelled here.
fn normalize_rotation(rotation: Option<i64>) -> f64 {
    match rotation {
        None => 0.0,
        Some(r) => (r as f64) * std::f64::consts::PI / 2.0,
    }
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
/// Reads exactly: `pin.position`, `comp.initial_rotation`,
/// `comp.initial_side`, `comp.initial_position`. `comp.initial_side or 0`
/// folds `None` to `0`, mirroring only side `1` (bottom) into an X mirror.
/// `comp.initial_position or (0.0, 0.0)` only ever fires on `None` -- a
/// non-`None` 2-tuple, even `(0.0, 0.0)` itself, is never falsy in Python.
fn pin_world_position(pin: &PinRow, comp: &ComponentRow) -> (f64, f64) {
    let rotation_rad = normalize_rotation(comp.initial_rotation);
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

type IdentityTuple = (String, String, String, f64, f64, Vec<i64>);
type PadWire = (String, String, String, f64, f64, Vec<i64>, f64, f64);

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

type TerminalTuple = (String, String, String, f64, f64, Vec<i64>, Vec<Option<String>>, bool);

/// `terminal_extraction.extract_net_terminals`.
///
/// `components` is a list of ``temper_design_bundle_python.Component``
/// pyclass instances (each with `.ref`, `.initial_position`,
/// `.initial_rotation`, `.initial_side`, `.pins` attributes).  Each
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
        let initial_rotation: Option<i64> = row.getattr("initial_rotation")?.extract()?;
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
            initial_rotation,
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

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(plan_terminal_tree_py, m)?)?;
    m.add_function(wrap_pyfunction!(extract_net_terminals_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
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

    #[test]
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

    #[test]
    fn plan_terminal_tree_rejects_empty_input() {
        assert!(plan_terminal_tree(&[]).is_err());
    }

    #[test]
    fn extract_net_terminals_skips_missing_component_and_pin() {
        let comp = ComponentRow {
            component_ref: "U1".to_string(),
            initial_position: Some((0.0, 0.0)),
            initial_rotation: None,
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

    #[test]
    fn extract_net_terminals_mirrors_bottom_side_before_rotating() {
        let comp = ComponentRow {
            component_ref: "U1".to_string(),
            initial_position: Some((5.0, 5.0)),
            initial_rotation: None,
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
}
