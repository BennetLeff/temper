// dsn_exporter: the SPECCTRA DSN emitter, ported from
// `temper_placer/io/dsn_exporter.py` (Wave-4 Phase-3 candidate 6).
//
// The contract is BYTE-IDENTICAL DSN output, not merely equivalent structure:
// `io/dsn_schema.py` hashes the design into a header that `io/dsn_validator.py`
// fails closed on, and `tests/io/test_dsn_kicad.py` pins the emitted file as
// importable by KiCad's SPECCTRA importer. Every construct below therefore
// replicates a *specific* CPython behaviour rather than an idiomatic Rust
// equivalent. The ones that differ if written naturally, and are pinned by the
// differential in `tests/io/test_dsn_rust_differential.py`:
//
//   * `py_round_half_even` — Python's builtin `round(float)` is round-half-to-
//     EVEN; `f64::round` is round-half-AWAY-from-zero. `round(0.5)` is 0 in
//     Python and 1.0 under `f64::round`. Every scaled DSN coordinate goes
//     through this, so the naive port would shift geometry by one 10um unit on
//     every exact .5 tick — and a board on a 5um grid hits exact .5 constantly.
//   * `natural_sort_key` — Python's `_natural_sort_key` splits on `(\d+)` and
//     maps digit runs through `int()`, so it compares numerically and
//     UNBOUNDED. Comparing the digit runs as strings would order `pin10`
//     before `pin2`, which is the exact thing the function exists to prevent.
//   * `py_lower` / `py_upper` — CPython's `str.lower()`/`str.upper()` are
//     per-character full mappings with NO context sensitivity. Rust's
//     `str::to_lowercase` applies the Greek final-sigma rule and would emit a
//     different sort key for a name ending in a capital sigma. Mapping
//     char-by-char reproduces CPython.
//   * insertion-ordered maps — `padstacks` and `components_by_fp` are plain
//     Python dicts, whose iteration order is insertion order *by language
//     guarantee* since 3.7, and the non-deterministic path emits them in that
//     order. A `HashMap` here would be the classic "ordering that happens to be
//     stable today"; `InsertionMap` below pins it explicitly.
//
// Two kernels are deliberately kept on the Python side of the boundary rather
// than reimplemented, because reimplementing them would CHANGE behaviour (the
// PR #688 `yaml.safe_load` judgement applied here) — see `DsnExporterInputs`.

use std::cmp::Ordering;
use std::collections::HashMap;
use std::sync::OnceLock;

use regex::Regex;

use crate::dsn_types::{DsnArg, DsnExpressionData};

/// Scale factor for the `(resolution um 10)` the exporter emits: 1 unit = 10um,
/// so 1mm = 100 units. Mirrors the `S = 100.0` local in every Python method.
const SCALE: f64 = 100.0;

// ---------------------------------------------------------------------------
// CPython primitive replicas
// ---------------------------------------------------------------------------

/// Python's builtin `round(x)` (no `ndigits`): nearest integer, ties to EVEN.
///
/// `f64::round` breaks ties away from zero and is therefore NOT a substitute:
/// `round(0.5) == 0` and `round(2.5) == 2` in Python, but `0.5f64.round()` is
/// `1.0` and `2.5f64.round()` is `3.0`.
///
/// Bound: Python's `int` is arbitrary precision, `i64` is not. Coordinates that
/// exceed `i64` saturate here where CPython would widen. A DSN coordinate is a
/// board dimension in 10um units, so the reachable range is ~1e6; the bound is
/// recorded in `VERIFICATION.md` rather than defended in code.
fn py_round_half_even(x: f64) -> i64 {
    let r = x.round_ties_even();
    if r >= i64::MAX as f64 {
        i64::MAX
    } else if r <= i64::MIN as f64 {
        i64::MIN
    } else {
        r as i64
    }
}

/// CPython `str.lower()`: a per-character full lowercase mapping.
///
/// Deliberately NOT `str::to_lowercase`, which additionally implements the
/// context-sensitive Greek final-sigma rule ("ΑΣ" lowercases to "ας" there but
/// to "ασ" in CPython). Sort keys are built from this, so the difference is
/// observable in element ordering.
fn py_lower(s: &str) -> String {
    s.chars().flat_map(char::to_lowercase).collect()
}

/// CPython `str.upper()`: a per-character full uppercase mapping.
fn py_upper(s: &str) -> String {
    s.chars().flat_map(char::to_uppercase).collect()
}

/// `format!("{:.prec$}")` matched to CPython's `f"{v:.Nf}"`. Both round the
/// exact binary value half-to-even at the requested decimal place.
fn py_format_fixed(v: f64, prec: usize) -> String {
    format!("{:.*}", prec, v)
}

/// One element of a `_natural_sort_key` result.
///
/// `re.split(r"(\d+)", s)` always yields text at even indices and a digit run
/// at odd indices, so two keys built from this function only ever compare
/// like-with-like at a given index. The cross-variant arms below exist to
/// satisfy `Ord`'s totality; they are unreachable for keys this module builds
/// (CPython would raise `TypeError` there rather than order them).
#[derive(Clone, PartialEq, Eq, Debug)]
enum NatPart {
    /// A `\d+` run with its leading zeros ALREADY STRIPPED, so that `Eq` and
    /// `Ord` agree (a normalizing comparison alone would make `Num("007")` and
    /// `Num("7")` unequal but `Ordering::Equal`, breaking `Ord`'s contract).
    /// Compared the way CPython compares the `int()` of it: more digits is
    /// greater, then lexicographic — exact for ASCII digits, and unbounded,
    /// which matters because Python's `int` has no width limit.
    Num(String),
    /// A non-digit run, already lowercased (Python does `part.lower()`).
    Text(String),
}

impl Ord for NatPart {
    fn cmp(&self, other: &Self) -> Ordering {
        match (self, other) {
            (NatPart::Num(a), NatPart::Num(b)) => {
                a.len().cmp(&b.len()).then_with(|| a.cmp(b))
            }
            (NatPart::Text(a), NatPart::Text(b)) => a.cmp(b),
            (NatPart::Num(_), NatPart::Text(_)) => Ordering::Less,
            (NatPart::Text(_), NatPart::Num(_)) => Ordering::Greater,
        }
    }
}

impl PartialOrd for NatPart {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

fn digit_run_pattern() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    #[expect(
        clippy::unwrap_used,
        reason = "literal pattern compiled from a source constant; cannot fail"
    )]
    RE.get_or_init(|| Regex::new(r"\d+").unwrap())
}

/// Port of `_natural_sort_key`: `re.split(r"(\d+)", s)` with digit runs mapped
/// through `int()` and every other run through `.lower()`.
///
/// `\d` here is the `regex` crate's Unicode `Nd` class, which is exactly what
/// Python's `re` module matches for `str` patterns — so a non-ASCII decimal
/// digit is split into a `Num` part on both sides.
fn natural_sort_key(s: &str) -> Vec<NatPart> {
    let mut parts = Vec::new();
    let mut last = 0usize;
    for m in digit_run_pattern().find_iter(s) {
        parts.push(NatPart::Text(py_lower(&s[last..m.start()])));
        parts.push(NatPart::Num(m.as_str().trim_start_matches('0').to_string()));
        last = m.end();
    }
    parts.push(NatPart::Text(py_lower(&s[last..])));
    parts
}

/// `str(x)` of a DSN argument, as the Python sort-key lambdas call it.
///
/// This is NOT `format_dsn_arg`: the lambdas take `str()` of the raw Python
/// object, so a string argument is returned bare (never quoted) and an int is
/// its decimal form. Using the DSN formatter here would quote net names
/// containing spaces and change the sort.
fn py_str_of_arg(arg: &DsnArg) -> String {
    match arg {
        DsnArg::Float(f) => py_repr_float(*f),
        DsnArg::Int(i) => i.to_string(),
        DsnArg::Str(s) | DsnArg::Raw(s) => s.clone(),
        DsnArg::Nested(e) => crate::dsn_types::dsn_expression_to_string(e),
    }
}

/// CPython `str(float)` — `repr`-shortest round-tripping form.
///
/// Only reachable from the sort-key lambdas, and only if a float ever lands in
/// a sorted-on position (none do today: the sorted positions carry `round()`
/// ints and `str`s). Kept exact anyway so the key function is total.
///
/// Delegates to `crate::stackup_validator::py_float_str`, the
/// empirically-verified CPython `repr(float)` replica (Debug `{:?}` shortest
/// round-trip + B10 exponent `+` sign and zero-padding). A local Display
/// (`{}`) implementation was previously used and diverged from CPython at
/// the `1e16` / `1e-4` fixed-point boundaries — `1e-5` rendered `"0.00001"`
/// instead of `"1e-05"`, `1e16` rendered `"10000000000000000.0"` instead of
/// `"1e+16"` (B10 bug, found by the 2026-08-10 io-types correctness sweep;
/// counter-examples pinned in `py_repr_float_b10_divergence_demonstrated`).
fn py_repr_float(f: f64) -> String {
    crate::stackup_validator::py_float_str(f)
}

// ---------------------------------------------------------------------------
// Insertion-ordered map
// ---------------------------------------------------------------------------

/// A `dict`-shaped map that iterates in INSERTION order, because that is what
/// the Python it replaces guarantees and what the non-deterministic export path
/// actually emits. Small by construction (padstacks per board, footprint ids
/// per board), so the linear index is not worth a dependency to avoid.
struct InsertionMap<V> {
    order: Vec<String>,
    index: HashMap<String, usize>,
    values: Vec<V>,
}

impl<V> InsertionMap<V> {
    fn new() -> Self {
        InsertionMap {
            order: Vec::new(),
            index: HashMap::new(),
            values: Vec::new(),
        }
    }

    fn contains_key(&self, k: &str) -> bool {
        self.index.contains_key(k)
    }

    /// `d[k] = v` — first insertion fixes the position, a later write to the
    /// same key overwrites in place (exactly CPython's dict semantics).
    fn insert(&mut self, k: String, v: V) {
        match self.index.get(&k) {
            Some(&i) => self.values[i] = v,
            None => {
                self.index.insert(k.clone(), self.values.len());
                self.order.push(k);
                self.values.push(v);
            }
        }
    }

    fn get_mut(&mut self, k: &str) -> Option<&mut V> {
        self.index.get(k).map(|&i| &mut self.values[i])
    }

    fn keys(&self) -> &[String] {
        &self.order
    }

    fn into_values(self) -> Vec<V> {
        self.values
    }
}

// ---------------------------------------------------------------------------
// Input model
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq)]
pub struct ExpLayer {
    pub name: String,
    pub layer_type: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExpPin {
    pub number: String,
    pub position: (f64, f64),
    pub width: f64,
    pub height: f64,
    pub shape: Option<String>,
    pub layer: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExpComponent {
    pub reference: String,
    pub footprint: String,
    pub pins: Vec<ExpPin>,
    pub initial_position: Option<(f64, f64)>,
    pub initial_rotation_quadrant: Option<i64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExpNet {
    pub name: String,
    pub pins: Vec<(String, String)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExpBoard {
    pub width: f64,
    pub height: f64,
    pub keepouts: Vec<(f64, f64, f64, f64)>,
    /// `None` mirrors a falsy `board.layer_stackup`.
    pub layers: Option<Vec<ExpLayer>>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExpTrace {
    pub layer: String,
    pub width: f64,
    pub start: (f64, f64),
    pub end: (f64, f64),
}

/// Everything the exporter reads, already lifted out of the Python objects.
///
/// Two fields carry values the Python shim computes and hands across rather
/// than the port recomputing them. Both are deliberate, and both would have
/// been behaviour changes rather than ports:
///
///   * `rotation_indices` — the Python takes `np.argmax(rotations, axis=1)` for
///     a 2-D input. Reimplementing argmax means re-deciding numpy's dtype
///     promotion and its tie-break, on an array this crate cannot see without
///     a numpy interop dependency the phase plan explicitly forbids assuming.
///     The shim runs the same `np.argmax` call the pre-migration code ran, so
///     the step is bit-identical by identity.
///   * `pin_world_positions` — `_compute_net_span` calls
///     `core.pin_geometry.pin_world_position`, the repo's single source of
///     truth for rotation-and-side-aware pad geometry, which is `sin`/`cos` on
///     `math.pi`. libm and Rust's intrinsics are not bit-identical across
///     platforms for transcendentals, so porting it would inject a divergence
///     into a *sort key* that no fixture-based differential would reliably
///     catch. The shim evaluates the same SSOT helper; the span arithmetic and
///     the ordering built on it are ported. Populated only when
///     `deterministic` is false, which is the only path that reads it.
pub struct DsnExporterInputs {
    pub board: ExpBoard,
    pub components: Vec<ExpComponent>,
    pub nets: Vec<ExpNet>,
    pub positions: Option<Vec<(f64, f64)>>,
    pub rotation_indices: Option<Vec<i64>>,
    pub deterministic: bool,
    /// `pin_world_positions[component_index][pin_index]`.
    pub pin_world_positions: Option<Vec<Vec<(f64, f64)>>>,
}

pub struct DsnExporterCore {
    inputs: DsnExporterInputs,
    center_offsets: Vec<(f64, f64)>,
    /// `Netlist._component_index`, built as `{c.ref: i for i, c in ...}` —
    /// so a duplicated ref resolves to the LAST occurrence, not the first.
    component_index: HashMap<String, usize>,
}

fn expr(name: &str, args: Vec<DsnArg>) -> DsnExpressionData {
    DsnExpressionData {
        name: name.to_string(),
        args,
        comment: None,
    }
}

fn nested(e: DsnExpressionData) -> DsnArg {
    DsnArg::Nested(Box::new(e))
}

fn s(v: &str) -> DsnArg {
    DsnArg::Str(v.to_string())
}

impl DsnExporterCore {
    pub fn new(inputs: DsnExporterInputs) -> Self {
        let center_offsets = Self::compute_center_offsets(&inputs.components);
        let mut component_index = HashMap::new();
        for (i, c) in inputs.components.iter().enumerate() {
            component_index.insert(c.reference.clone(), i);
        }
        DsnExporterCore {
            inputs,
            center_offsets,
            component_index,
        }
    }

    pub fn center_offsets(&self) -> &[(f64, f64)] {
        &self.center_offsets
    }

    /// Port of `_compute_center_offsets`. The float operation ORDER is load
    /// bearing: `(min + max) / 2` on the pad-inclusive bounding box, with the
    /// half-extents taken as `pin.width / 2` before the min/max, exactly as the
    /// Python evaluates them.
    fn compute_center_offsets(components: &[ExpComponent]) -> Vec<(f64, f64)> {
        let mut offsets = Vec::with_capacity(components.len());
        for comp in components {
            if comp.pins.is_empty() {
                offsets.push((0.0, 0.0));
                continue;
            }
            let mut min_x = f64::INFINITY;
            let mut max_x = f64::NEG_INFINITY;
            let mut min_y = f64::INFINITY;
            let mut max_y = f64::NEG_INFINITY;
            for pin in &comp.pins {
                let (px, py) = pin.position;
                let half_w = pin.width / 2.0;
                let half_h = pin.height / 2.0;
                min_x = py_min(min_x, px - half_w);
                max_x = py_max(max_x, px + half_w);
                min_y = py_min(min_y, py - half_h);
                max_y = py_max(max_y, py + half_h);
            }
            offsets.push(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0));
        }
        offsets
    }

    /// The layer names the emitter uses, and whether the stackup was present.
    fn layer_names(&self) -> Vec<String> {
        match &self.inputs.board.layers {
            Some(layers) if !layers.is_empty() => layers.iter().map(|l| l.name.clone()).collect(),
            Some(_) | None => vec!["F.Cu".to_string(), "B.Cu".to_string()],
        }
    }

    fn has_stackup(&self) -> bool {
        matches!(&self.inputs.board.layers, Some(l) if !l.is_empty())
    }

    // -- structure ----------------------------------------------------------

    pub fn export_structure(&self, all_layers_signal: bool) -> DsnExpressionData {
        let mut layer_exprs: Vec<DsnArg> = Vec::new();
        let mut layer_names: Vec<String> = Vec::new();

        if self.has_stackup() {
            let layers = self.inputs.board.layers.as_deref().unwrap_or(&[]);
            for (i, layer) in layers.iter().enumerate() {
                // `"signal" if all_layers_signal else ("signal" if
                // layer.layer_type == "signal" else "power")` — flattened; the
                // two "signal" arms are one condition.
                let ltype = if all_layers_signal || layer.layer_type == "signal" {
                    "signal"
                } else {
                    "power"
                };
                layer_names.push(layer.name.clone());
                layer_exprs.push(nested(expr(
                    "layer",
                    vec![
                        s(&layer.name),
                        nested(expr("type", vec![s(ltype)])),
                        nested(expr(
                            "property",
                            vec![nested(expr("index", vec![DsnArg::Int(i as i64)]))],
                        )),
                    ],
                )));
            }
        } else {
            layer_names = vec!["F.Cu".to_string(), "B.Cu".to_string()];
            for (i, name) in ["F.Cu", "B.Cu"].iter().enumerate() {
                layer_exprs.push(nested(expr(
                    "layer",
                    vec![
                        s(name),
                        nested(expr("type", vec![s("signal")])),
                        nested(expr(
                            "property",
                            vec![nested(expr("index", vec![DsnArg::Int(i as i64)]))],
                        )),
                    ],
                )));
            }
        }

        let boundary = nested(expr(
            "boundary",
            vec![nested(expr(
                "rect",
                vec![
                    s("pcb"),
                    DsnArg::Int(0),
                    DsnArg::Int(0),
                    DsnArg::Int(py_round_half_even(self.inputs.board.width * SCALE)),
                    DsnArg::Int(py_round_half_even(self.inputs.board.height * SCALE)),
                ],
            ))],
        ));

        let keepout_layer = layer_names
            .first()
            .cloned()
            .unwrap_or_else(|| "F.Cu".to_string());
        let mut keepout_exprs: Vec<DsnExpressionData> = Vec::new();
        for (i, ko) in self.inputs.board.keepouts.iter().enumerate() {
            keepout_exprs.push(expr(
                "keepout",
                vec![
                    DsnArg::Str(format!("KO_{}", i)),
                    nested(expr(
                        "rect",
                        vec![
                            s(&keepout_layer),
                            DsnArg::Int(py_round_half_even(ko.0 * SCALE)),
                            DsnArg::Int(py_round_half_even(ko.1 * SCALE)),
                            DsnArg::Int(py_round_half_even(ko.2 * SCALE)),
                            DsnArg::Int(py_round_half_even(ko.3 * SCALE)),
                        ],
                    )),
                ],
            ));
        }
        if self.inputs.deterministic {
            // `key=lambda k: str(k.args[0]) if k.args else ""` — a plain string
            // sort of "KO_<i>", so KO_10 precedes KO_2. Stable, like list.sort.
            keepout_exprs.sort_by(|a, b| {
                let ka = a.args.first().map(py_str_of_arg).unwrap_or_default();
                let kb = b.args.first().map(py_str_of_arg).unwrap_or_default();
                ka.cmp(&kb)
            });
        }

        let mut args = layer_exprs;
        args.push(boundary);
        args.extend(keepout_exprs.into_iter().map(nested));
        args.push(nested(expr("via", vec![s("VIA")])));
        args.push(nested(expr(
            "rule",
            vec![
                nested(expr("width", vec![DsnArg::Int(13)])),
                nested(expr("clearance", vec![DsnArg::Int(12)])),
            ],
        )));
        expr("structure", args)
    }

    // -- library ------------------------------------------------------------

    /// The padstack name for a pin. Shared by the padstack-creation pass and
    /// the image pass, which build it from the same pieces in the Python.
    fn padstack_name(pin: &ExpPin) -> String {
        let mut shape_name = pin.shape.clone().unwrap_or_else(|| "rect".to_string());
        if shape_name.is_empty() {
            // `pin.shape if pin.shape else "rect"` — an empty string is falsy.
            shape_name = "rect".to_string();
        }
        if shape_name == "thru_hole" {
            shape_name = "circle".to_string();
        }
        let layer_suffix = if pin.layer != "all" {
            format!("_{}", pin.layer.replace('.', "_"))
        } else {
            "_ALL".to_string()
        };
        let dims_str = format!(
            "{}x{}",
            py_format_fixed(pin.width, 3),
            py_format_fixed(pin.height, 3)
        )
        .replace('.', "_");
        format!(
            "PS_{}_{}{}",
            py_upper(&shape_name),
            dims_str,
            layer_suffix
        )
    }

    fn normalized_shape(pin: &ExpPin) -> String {
        let mut shape_name = pin.shape.clone().unwrap_or_else(|| "rect".to_string());
        if shape_name.is_empty() {
            shape_name = "rect".to_string();
        }
        if shape_name == "thru_hole" {
            shape_name = "circle".to_string();
        }
        shape_name
    }

    fn image_id(comp: &ExpComponent) -> String {
        format!(
            "{}_{}",
            // `.replace(':', '_').replace('/', '_')` — one pass is
            // equivalent here: both map to the same character and neither
            // introduces the other.
            comp.footprint.replace([':', '/'], "_"),
            comp.reference
        )
    }

    pub fn export_library(&self) -> DsnExpressionData {
        let mut images: Vec<DsnExpressionData> = Vec::new();
        let mut padstacks: InsertionMap<DsnExpressionData> = InsertionMap::new();

        let layer_names = self.layer_names();

        let via_shapes: Vec<DsnArg> = layer_names
            .iter()
            .map(|ln| {
                nested(expr(
                    "shape",
                    vec![nested(expr(
                        "circle",
                        vec![s(ln), DsnArg::Float(0.6 * SCALE)],
                    ))],
                ))
            })
            .collect();
        {
            let mut args = vec![s("VIA")];
            args.extend(via_shapes);
            padstacks.insert("VIA".to_string(), expr("padstack", args));
        }

        for (i, comp) in self.inputs.components.iter().enumerate() {
            let (center_offset_x, center_offset_y) = self.center_offsets[i];

            // 1. padstacks for unique pad shapes/sizes
            for pin in &comp.pins {
                let ps_name = Self::padstack_name(pin);
                if !padstacks.contains_key(&ps_name) {
                    let pad_width = pin.width;
                    let pad_height = pin.height;
                    // `-pad_width / 2 * S` parses as `((-pad_width) / 2) * S`.
                    let x1 = -pad_width / 2.0 * SCALE;
                    let y1 = -pad_height / 2.0 * SCALE;
                    let x2 = pad_width / 2.0 * SCALE;
                    let y2 = pad_height / 2.0 * SCALE;

                    let shape_name = Self::normalized_shape(pin);
                    let layers_to_add: Vec<String> = if pin.layer == "all" {
                        layer_names.clone()
                    } else {
                        vec![pin.layer.clone()]
                    };
                    let mut shapes: Vec<DsnArg> = Vec::new();
                    for layer in &layers_to_add {
                        if shape_name == "circle" {
                            shapes.push(nested(expr(
                                "shape",
                                vec![nested(expr(
                                    "circle",
                                    vec![s(layer), DsnArg::Float(pad_width * SCALE)],
                                ))],
                            )));
                        } else {
                            shapes.push(nested(expr(
                                "shape",
                                vec![nested(expr(
                                    "rect",
                                    vec![
                                        s(layer),
                                        DsnArg::Float(x1),
                                        DsnArg::Float(y1),
                                        DsnArg::Float(x2),
                                        DsnArg::Float(y2),
                                    ],
                                ))],
                            )));
                        }
                    }
                    let mut args = vec![DsnArg::Str(ps_name.clone())];
                    args.extend(shapes);
                    padstacks.insert(ps_name, expr("padstack", args));
                }
            }

            // 2. the image (footprint), unique per component instance
            let fp_id = Self::image_id(comp);
            let mut pins: Vec<DsnExpressionData> = Vec::new();
            for pin in &comp.pins {
                let ps_name = Self::padstack_name(pin);
                let centered_x = pin.position.0 - center_offset_x;
                let centered_y = pin.position.1 - center_offset_y;
                pins.push(expr(
                    "pin",
                    vec![
                        DsnArg::Str(ps_name),
                        DsnArg::Str(pin.number.clone()),
                        DsnArg::Int(py_round_half_even(centered_x * SCALE)),
                        DsnArg::Int(py_round_half_even(centered_y * SCALE)),
                    ],
                ));
            }

            // First sort: by the natural key of args[2] — the SCALED X
            // COORDINATE, not the pin number. It is a `str()` of a Python int,
            // so "-150" keys as ['-', 150, ''] and negative coordinates order
            // by magnitude ASCENDING after the '-' text part. Faithfully odd;
            // preserved because the second sort is stable and inherits it as
            // the tie-break.
            if self.inputs.deterministic {
                sort_by_key_stable(&mut pins, |p| {
                    p.args
                        .get(2)
                        .map(|a| natural_sort_key(&py_str_of_arg(a)))
                        .unwrap_or_default()
                });
            }

            // Footprints with no pins get a 1mm keepout outline so the router
            // does not treat them as empty space.
            if pins.is_empty() {
                let l0 = layer_names
                    .first()
                    .cloned()
                    .unwrap_or_else(|| "F.Cu".to_string());
                pins.push(expr(
                    "outline",
                    vec![nested(expr(
                        "rect",
                        vec![
                            DsnArg::Str(l0),
                            DsnArg::Float(-0.5 * SCALE),
                            DsnArg::Float(-0.5 * SCALE),
                            DsnArg::Float(0.5 * SCALE),
                            DsnArg::Float(0.5 * SCALE),
                        ],
                    ))],
                ));
            }

            // Second sort: by the natural key of args[1] — the pin number.
            // Stable, so ties keep the x-coordinate order from the first sort.
            // The `len(p.args) > 1` guard only fires for the lone `outline`
            // expression, which is never in a list with anything else.
            if self.inputs.deterministic {
                sort_by_key_stable(&mut pins, |p| {
                    if p.args.len() > 1 {
                        p.args
                            .get(1)
                            .map(|a| natural_sort_key(&py_str_of_arg(a)))
                            .unwrap_or_default()
                    } else {
                        vec![NatPart::Text("0".to_string())]
                    }
                });
            }

            let mut args = vec![DsnArg::Str(fp_id)];
            args.extend(pins.into_iter().map(nested));
            images.push(expr("image", args));
        }

        if self.inputs.deterministic {
            sort_by_key_stable(&mut images, |img| {
                img.args.first().map(py_str_of_arg).map(|v| py_lower(&v))
            });
        }

        let mut ps_values = padstacks.into_values();
        if self.inputs.deterministic {
            sort_by_key_stable(&mut ps_values, |ps| {
                ps.args.first().map(py_str_of_arg).map(|v| py_lower(&v))
            });
        }

        let mut args: Vec<DsnArg> = Vec::with_capacity(images.len() + ps_values.len());
        args.extend(images.into_iter().map(nested));
        args.extend(ps_values.into_iter().map(nested));
        expr("library", args)
    }

    // -- placement ----------------------------------------------------------

    pub fn export_placement(&self) -> DsnExpressionData {
        let mut components_by_fp: InsertionMap<Vec<DsnExpressionData>> = InsertionMap::new();

        for (i, comp) in self.inputs.components.iter().enumerate() {
            let fp_id = Self::image_id(comp);
            if !components_by_fp.contains_key(&fp_id) {
                components_by_fp.insert(fp_id.clone(), Vec::new());
            }

            let (mut x, mut y) = match &self.inputs.positions {
                Some(p) => p[i],
                None => comp.initial_position.unwrap_or((0.0, 0.0)),
            };

            let (center_offset_x, center_offset_y) = self.center_offsets[i];
            x += center_offset_x;
            y += center_offset_y;

            let rot = match &self.inputs.rotation_indices {
                Some(r) => r[i] * 90,
                // `(comp.initial_rotation_quadrant or 0) * 90` — `None` and `0` both
                // fall through to 0.
                None => comp.initial_rotation_quadrant.unwrap_or(0) * 90,
            };

            let side = match comp.pins.first() {
                Some(p) if p.layer == "B.Cu" => "back",
                _ => "front",
            };

            if let Some(bucket) = components_by_fp.get_mut(&fp_id) {
                bucket.push(expr(
                    "place",
                    vec![
                        DsnArg::Str(comp.reference.clone()),
                        DsnArg::Float(x * SCALE),
                        DsnArg::Float(y * SCALE),
                        s(side),
                        DsnArg::Float(rot as f64),
                    ],
                ));
            }
        }

        let mut comp_exprs: Vec<DsnExpressionData> = Vec::new();
        if self.inputs.deterministic {
            let mut sorted_fp_ids: Vec<String> = components_by_fp.keys().to_vec();
            sort_by_key_stable(&mut sorted_fp_ids, |k| py_lower(k));
            for fp_id in &sorted_fp_ids {
                let mut instances = components_by_fp
                    .get_mut(fp_id)
                    .map(std::mem::take)
                    .unwrap_or_default();
                sort_by_key_stable(&mut instances, |inst| {
                    inst.args.first().map(py_str_of_arg).map(|v| py_lower(&v))
                });
                let mut args = vec![DsnArg::Str(fp_id.clone())];
                args.extend(instances.into_iter().map(nested));
                comp_exprs.push(expr("component", args));
            }
            // The Python re-sorts the already-sorted list; kept because a
            // stable no-op re-sort is still observable if the two keys ever
            // disagree (they cannot today — same key, same source).
            sort_by_key_stable(&mut comp_exprs, |c| {
                c.args.first().map(py_str_of_arg).map(|v| py_lower(&v))
            });
        } else {
            let keys: Vec<String> = components_by_fp.keys().to_vec();
            for fp_id in &keys {
                let instances = components_by_fp
                    .get_mut(fp_id)
                    .map(std::mem::take)
                    .unwrap_or_default();
                let mut args = vec![DsnArg::Str(fp_id.clone())];
                args.extend(instances.into_iter().map(nested));
                comp_exprs.push(expr("component", args));
            }
        }

        expr(
            "placement",
            comp_exprs.into_iter().map(nested).collect::<Vec<_>>(),
        )
    }

    // -- network ------------------------------------------------------------

    /// Port of `_compute_net_span`: the HPWL span of a net's pins, used only as
    /// a non-deterministic ordering key.
    ///
    /// The Python's `base_x`/`base_y` locals are computed and never read, so
    /// the span comes purely from `pin_world_position`. They are NOT fully
    /// dead, though: `self.positions[comp_idx, 0]` is evaluated inside the
    /// `except (KeyError, IndexError): continue`, so when a caller passes a
    /// `positions` array with fewer rows than there are components, numpy
    /// raises `IndexError` and the pin is SKIPPED rather than contributing to
    /// the span. The `positions_len` guard below reproduces that skip; only the
    /// unobservable arithmetic is dropped.
    fn compute_net_span(&self, net: &ExpNet) -> f64 {
        if net.pins.len() < 2 {
            return 0.0;
        }
        let world = match &self.inputs.pin_world_positions {
            Some(w) => w,
            None => return 0.0,
        };
        let mut xs: Vec<f64> = Vec::new();
        let mut ys: Vec<f64> = Vec::new();
        for (comp_ref, pin_num) in &net.pins {
            // `except (KeyError, IndexError): continue`
            let Some(&comp_idx) = self.component_index.get(comp_ref) else {
                continue;
            };
            let Some(comp) = self.inputs.components.get(comp_idx) else {
                continue;
            };
            // The `self.positions[comp_idx, 0]` IndexError path (see above).
            if let Some(p) = &self.inputs.positions
                && comp_idx >= p.len()
            {
                continue;
            }
            for (pin_idx, pin) in comp.pins.iter().enumerate() {
                if &pin.number == pin_num {
                    if let Some((wx, wy)) = world.get(comp_idx).and_then(|c| c.get(pin_idx)) {
                        xs.push(*wx);
                        ys.push(*wy);
                    }
                    break;
                }
            }
        }
        if xs.len() < 2 {
            return 0.0;
        }
        let (min_x, max_x) = min_max(&xs);
        let (min_y, max_y) = min_max(&ys);
        (max_x - min_x) + (max_y - min_y)
    }

    fn voltage_pattern() -> &'static Regex {
        static RE: OnceLock<Regex> = OnceLock::new();
        #[expect(
            clippy::unwrap_used,
            reason = "literal pattern compiled from a source constant; cannot fail"
        )]
        RE.get_or_init(|| {
            // Python: re.compile(r"(_PLUS|VCC|VDD)\d+V?\d*$", re.IGNORECASE)
            //
            // `\n?\z` rather than `$`: in Python (without re.MULTILINE) `$`
            // also matches immediately BEFORE a trailing newline, whereas the
            // regex crate's `$` is end-of-haystack only. A net name ending in
            // "\n" would otherwise classify as signal here and power there.
            Regex::new(r"(?i)(_PLUS|VCC|VDD)\d+V?\d*\n?\z").unwrap()
        })
    }

    pub fn export_network(
        &self,
        use_net_classes: bool,
        exclude_nets: Option<&[String]>,
    ) -> DsnExpressionData {
        let mut net_exprs: Vec<DsnExpressionData> = Vec::new();
        let mut power_nets: Vec<String> = Vec::new();
        let mut signal_nets: Vec<String> = Vec::new();

        const POWER_PREFIXES: [&str; 7] =
            ["GND", "PGND", "CGND", "VCC", "VDD", "DC_BUS", "_PLUS"];

        let mut sorted_nets: Vec<&ExpNet> = self.inputs.nets.iter().collect();
        if self.inputs.deterministic {
            sort_by_key_stable(&mut sorted_nets, |n| {
                py_lower(&n.name.replace('+', "_PLUS").replace('-', "_MINUS"))
            });
        } else {
            // `key=lambda n: (len(n.pins), self._compute_net_span(n))`
            let keys: Vec<(usize, f64)> = self
                .inputs
                .nets
                .iter()
                .map(|n| (n.pins.len(), self.compute_net_span(n)))
                .collect();
            let mut idx: Vec<usize> = (0..sorted_nets.len()).collect();
            idx.sort_by(|&a, &b| {
                keys[a].0.cmp(&keys[b].0).then_with(|| {
                    keys[a]
                        .1
                        .partial_cmp(&keys[b].1)
                        .unwrap_or(Ordering::Equal)
                })
            });
            sorted_nets = idx.into_iter().map(|i| &self.inputs.nets[i]).collect();
        }

        for net in sorted_nets {
            let clean_name = net.name.replace('+', "_PLUS").replace('-', "_MINUS");
            if let Some(ex) = exclude_nets
                && ex.iter().any(|e| e == &net.name || e == &clean_name)
            {
                continue;
            }
            let pin_refs: Vec<DsnArg> = net
                .pins
                .iter()
                .map(|(comp_ref, pin_num)| DsnArg::Str(format!("{}-{}", comp_ref, pin_num)))
                .collect();

            if !pin_refs.is_empty() {
                net_exprs.push(expr(
                    "net",
                    vec![
                        DsnArg::Str(clean_name.clone()),
                        nested(expr("pins", pin_refs)),
                    ],
                ));

                let upper_name = py_upper(&clean_name);
                let is_power = POWER_PREFIXES.iter().any(|p| upper_name.starts_with(p))
                    || Self::voltage_pattern().is_match(&clean_name);
                if is_power {
                    power_nets.push(clean_name);
                } else {
                    signal_nets.push(clean_name);
                }
            }
        }

        if use_net_classes && !(power_nets.is_empty() && signal_nets.is_empty()) {
            let mut class_exprs: Vec<DsnExpressionData> = Vec::new();

            let mut inner_layers: Vec<String> = Vec::new();
            let mut outer_layers: Vec<String> = Vec::new();
            if self.has_stackup() {
                for ly in self.inputs.board.layers.as_deref().unwrap_or(&[]) {
                    if ly.layer_type == "plane" || ly.layer_type == "mixed" {
                        inner_layers.push(ly.name.clone());
                    } else {
                        outer_layers.push(ly.name.clone());
                    }
                }
            } else {
                outer_layers = vec!["F.Cu".to_string(), "B.Cu".to_string()];
            }

            if !power_nets.is_empty() {
                let mut items: Vec<DsnArg> = vec![s("power")];
                items.extend(power_nets.iter().map(|n| DsnArg::Str(n.clone())));
                items.push(nested(expr(
                    "circuit",
                    vec![nested(expr("use_via", vec![s("VIA")]))],
                )));
                items.push(nested(expr(
                    "rule",
                    vec![
                        nested(expr("width", vec![DsnArg::Int(25)])),
                        nested(expr("clearance", vec![DsnArg::Int(20)])),
                    ],
                )));
                let mut all_layers = outer_layers.clone();
                all_layers.extend(inner_layers.iter().cloned());
                if !all_layers.is_empty() {
                    items.push(nested(expr(
                        "use_layer",
                        all_layers.iter().map(|l| DsnArg::Str(l.clone())).collect(),
                    )));
                }
                class_exprs.push(expr("class", items));
            }

            if !signal_nets.is_empty() {
                let mut items: Vec<DsnArg> = vec![s("signal")];
                items.extend(signal_nets.iter().map(|n| DsnArg::Str(n.clone())));
                items.push(nested(expr(
                    "circuit",
                    vec![nested(expr("use_via", vec![s("VIA")]))],
                )));
                items.push(nested(expr(
                    "rule",
                    vec![
                        nested(expr("width", vec![DsnArg::Int(13)])),
                        nested(expr("clearance", vec![DsnArg::Int(12)])),
                    ],
                )));
                if !outer_layers.is_empty() {
                    items.push(nested(expr(
                        "use_layer",
                        outer_layers.iter().map(|l| DsnArg::Str(l.clone())).collect(),
                    )));
                }
                class_exprs.push(expr("class", items));
            }

            let mut args: Vec<DsnArg> = net_exprs.into_iter().map(nested).collect();
            args.extend(class_exprs.into_iter().map(nested));
            return expr("network", args);
        }

        expr(
            "network",
            net_exprs.into_iter().map(nested).collect::<Vec<_>>(),
        )
    }

    // -- wiring / pcb -------------------------------------------------------

    pub fn export_wiring(&self, traces: &[ExpTrace]) -> DsnExpressionData {
        let wires: Vec<DsnArg> = traces
            .iter()
            .map(|t| {
                nested(expr(
                    "wire",
                    vec![nested(expr(
                        "path",
                        vec![
                            s(&t.layer),
                            DsnArg::Float(t.width),
                            DsnArg::Float(t.start.0),
                            DsnArg::Float(t.start.1),
                            DsnArg::Float(t.end.0),
                            DsnArg::Float(t.end.1),
                        ],
                    ))],
                ))
            })
            .collect();
        expr("wiring", wires)
    }

    /// `schema_hash` is supplied by the caller rather than recomputed here: the
    /// hash already lives in the `temper-dsn` crate behind
    /// `io/dsn_schema.py::compute_dsn_schema_hash`, which was a Rust delegation
    /// shim BEFORE this migration. Re-implementing it in this crate would fork
    /// the definition of a value that `io/dsn_validator.py` fails closed on —
    /// two implementations of one contractual hash is exactly the drift the
    /// validator exists to catch. The shim calls the existing SSOT.
    pub fn export_pcb(
        &self,
        pcb_name: &str,
        traces: Option<&[ExpTrace]>,
        exclude_nets: Option<&[String]>,
        schema_hash: Option<&str>,
    ) -> DsnExpressionData {
        let mut sections: Vec<DsnArg> = vec![
            nested(expr(
                "parser",
                vec![
                    nested(expr("string_quote", vec![s("\"")])),
                    nested(expr("space_in_quoted_tokens", vec![s("on")])),
                ],
            )),
            nested(expr("resolution", vec![s("um"), DsnArg::Int(10)])),
            nested(expr("unit", vec![s("mm")])),
            nested(self.export_structure(true)),
            nested(self.export_library()),
            nested(self.export_placement()),
            nested(self.export_network(true, exclude_nets)),
        ];

        // `if traces:` — an empty list is falsy, so no `(wiring)` section.
        if let Some(t) = traces
            && !t.is_empty()
        {
            sections.push(nested(self.export_wiring(t)));
        }

        let mut args = vec![DsnArg::Str(pcb_name.to_string())];
        args.extend(sections);
        let mut pcb_expr = expr("pcb", args);

        if self.inputs.deterministic
            && let Some(h) = schema_hash
        {
            pcb_expr.comment = Some(format!("schema-version: sha256:{}", h));
        }
        pcb_expr
    }
}

/// Python's `min`/`max` return the FIRST argument on a tie and propagate a NaN
/// second argument only when the comparison is false; `f64::min`/`f64::max`
/// silently drop NaN. Written out so the NaN path is the Python one.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

fn min_max(v: &[f64]) -> (f64, f64) {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for &x in v {
        lo = py_min(lo, x);
        hi = py_max(hi, x);
    }
    (lo, hi)
}

/// `list.sort(key=...)` — STABLE, and the key is computed once per element
/// (which matters only for cost here, not semantics).
fn sort_by_key_stable<T, K: Ord, F: FnMut(&T) -> K>(v: &mut [T], key: F) {
    v.sort_by_key(key);
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;
    use crate::dsn_types::DSNExpression;
    use pyo3::prelude::*;
    use std::panic::{AssertUnwindSafe, catch_unwind};

    /// Every `#[pymethods]` body runs inside this. A panic unwinding into the
    /// CPython frame is undefined behaviour; this converts it to a
    /// `RuntimeError` at the boundary (repo Rust practice R1g).
    fn guard<R>(f: impl FnOnce() -> R) -> PyResult<R> {
        catch_unwind(AssertUnwindSafe(f)).map_err(|e| {
            let detail = e
                .downcast_ref::<&str>()
                .map(|s| (*s).to_string())
                .or_else(|| e.downcast_ref::<String>().cloned())
                .unwrap_or_else(|| "unknown panic".to_string());
            pyo3::exceptions::PyRuntimeError::new_err(format!(
                "panic in temper_io_types DSN exporter: {detail}"
            ))
        })
    }

    fn wrap(py: Python<'_>, data: DsnExpressionData) -> PyResult<Py<DSNExpression>> {
        Py::new(py, DSNExpression::from_data(data))
    }

    /// Read the fields the exporter uses off a duck-typed Python object, the
    /// `from_py_object` boundary the phase plan's D5 established for
    /// `serialize_boardstate_to_dsn`.
    fn read_board(board: &Bound<'_, PyAny>) -> PyResult<ExpBoard> {
        let width: f64 = board.getattr("width")?.extract()?;
        let height: f64 = board.getattr("height")?.extract()?;
        let keepouts: Vec<(f64, f64, f64, f64)> = board.getattr("keepouts")?.extract()?;

        let stackup = board.getattr("layer_stackup")?;
        // `if self.board.layer_stackup:` — truthiness, not `is not None`.
        let layers = if stackup.is_truthy()? {
            let mut out = Vec::new();
            for ly in stackup.getattr("layers")?.try_iter()? {
                let ly = ly?;
                out.push(ExpLayer {
                    name: ly.getattr("name")?.extract()?,
                    layer_type: ly.getattr("layer_type")?.extract()?,
                });
            }
            Some(out)
        } else {
            None
        };

        Ok(ExpBoard {
            width,
            height,
            keepouts,
            layers,
        })
    }

    fn read_pin(pin: &Bound<'_, PyAny>) -> PyResult<ExpPin> {
        Ok(ExpPin {
            number: pin.getattr("number")?.extract()?,
            position: pin.getattr("position")?.extract()?,
            width: pin.getattr("width")?.extract()?,
            height: pin.getattr("height")?.extract()?,
            shape: pin.getattr("shape")?.extract()?,
            layer: pin.getattr("layer")?.extract()?,
        })
    }

    fn read_netlist(netlist: &Bound<'_, PyAny>) -> PyResult<(Vec<ExpComponent>, Vec<ExpNet>)> {
        let mut components = Vec::new();
        for comp in netlist.getattr("components")?.try_iter()? {
            let comp = comp?;
            let mut pins = Vec::new();
            for pin in comp.getattr("pins")?.try_iter()? {
                pins.push(read_pin(&pin?)?);
            }
            components.push(ExpComponent {
                reference: comp.getattr("ref")?.extract()?,
                footprint: comp.getattr("footprint")?.extract()?,
                pins,
                initial_position: comp.getattr("initial_position")?.extract()?,
                initial_rotation_quadrant: comp.getattr("initial_rotation_quadrant")?.extract()?,
            });
        }
        let mut nets = Vec::new();
        for net in netlist.getattr("nets")?.try_iter()? {
            let net = net?;
            nets.push(ExpNet {
                name: net.getattr("name")?.extract()?,
                pins: net.getattr("pins")?.extract()?,
            });
        }
        Ok((components, nets))
    }

    fn read_traces(traces: &Bound<'_, PyAny>) -> PyResult<Vec<ExpTrace>> {
        let mut out = Vec::new();
        for t in traces.try_iter()? {
            let t = t?;
            out.push(ExpTrace {
                layer: t.getattr("layer")?.extract()?,
                width: t.getattr("width")?.extract()?,
                start: t.getattr("start")?.extract()?,
                end: t.getattr("end")?.extract()?,
            });
        }
        Ok(out)
    }

    /// The migrated exporter. `temper_placer.io.dsn_exporter.DSNExporter` is a
    /// delegation shim over this: it keeps the numpy-typed attributes and the
    /// two kernels named in `DsnExporterInputs`, and forwards every export
    /// method here.
    #[pyclass(name = "DSNExporterCore")]
    pub struct PyDsnExporterCore {
        core: DsnExporterCore,
    }

    #[pymethods]
    impl PyDsnExporterCore {
        #[new]
        #[pyo3(signature = (
            board,
            netlist,
            positions = None,
            rotation_indices = None,
            deterministic = true,
            pin_world_positions = None,
        ))]
        fn new(
            board: &Bound<'_, PyAny>,
            netlist: &Bound<'_, PyAny>,
            positions: Option<Vec<(f64, f64)>>,
            rotation_indices: Option<Vec<i64>>,
            deterministic: bool,
            pin_world_positions: Option<Vec<Vec<(f64, f64)>>>,
        ) -> PyResult<Self> {
            let board = read_board(board)?;
            let (components, nets) = read_netlist(netlist)?;
            let inputs = DsnExporterInputs {
                board,
                components,
                nets,
                positions,
                rotation_indices,
                deterministic,
                pin_world_positions,
            };
            guard(move || PyDsnExporterCore {
                core: DsnExporterCore::new(inputs),
            })
        }

        #[getter]
        fn center_offsets(&self) -> Vec<(f64, f64)> {
            self.core.center_offsets().to_vec()
        }

        #[pyo3(signature = (all_layers_signal = true))]
        fn export_structure(
            &self,
            py: Python<'_>,
            all_layers_signal: bool,
        ) -> PyResult<Py<DSNExpression>> {
            let data = guard(|| self.core.export_structure(all_layers_signal))?;
            wrap(py, data)
        }

        fn export_library(&self, py: Python<'_>) -> PyResult<Py<DSNExpression>> {
            let data = guard(|| self.core.export_library())?;
            wrap(py, data)
        }

        fn export_placement(&self, py: Python<'_>) -> PyResult<Py<DSNExpression>> {
            let data = guard(|| self.core.export_placement())?;
            wrap(py, data)
        }

        #[pyo3(signature = (use_net_classes = true, exclude_nets = None))]
        fn export_network(
            &self,
            py: Python<'_>,
            use_net_classes: bool,
            exclude_nets: Option<Vec<String>>,
        ) -> PyResult<Py<DSNExpression>> {
            let data = guard(|| self.core.export_network(use_net_classes, exclude_nets.as_deref()))?;
            wrap(py, data)
        }

        fn export_wiring(
            &self,
            py: Python<'_>,
            traces: &Bound<'_, PyAny>,
        ) -> PyResult<Py<DSNExpression>> {
            let traces = read_traces(traces)?;
            let data = guard(|| self.core.export_wiring(&traces))?;
            wrap(py, data)
        }

        #[pyo3(signature = (pcb_name = "temper".to_string(), traces = None, exclude_nets = None, schema_hash = None))]
        fn export_pcb(
            &self,
            py: Python<'_>,
            pcb_name: String,
            traces: Option<&Bound<'_, PyAny>>,
            exclude_nets: Option<Vec<String>>,
            schema_hash: Option<String>,
        ) -> PyResult<Py<DSNExpression>> {
            let traces = match traces {
                Some(t) if !t.is_none() => Some(read_traces(t)?),
                _ => None,
            };
            let data = guard(|| {
                self.core.export_pcb(
                    &pcb_name,
                    traces.as_deref(),
                    exclude_nets.as_deref(),
                    schema_hash.as_deref(),
                )
            })?;
            wrap(py, data)
        }
    }
}

#[cfg(feature = "python")]
pub use py_bridge::PyDsnExporterCore;

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn round_is_half_to_even_not_half_away() {
        // The whole point: f64::round would give 1, 3, -1, -3 here.
        assert_eq!(py_round_half_even(0.5), 0);
        assert_eq!(py_round_half_even(1.5), 2);
        assert_eq!(py_round_half_even(2.5), 2);
        assert_eq!(py_round_half_even(3.5), 4);
        assert_eq!(py_round_half_even(-0.5), 0);
        assert_eq!(py_round_half_even(-2.5), -2);
        assert_eq!(py_round_half_even(1.4), 1);
        assert_eq!(py_round_half_even(1.6), 2);
    }

    #[cfg_attr(test, test)]
    fn natural_key_orders_numerically_not_lexically() {
        let mut v = vec!["pin10", "pin2", "pin1"];
        v.sort_by_key(|a| natural_sort_key(a));
        assert_eq!(v, vec!["pin1", "pin2", "pin10"]);
    }

    #[cfg_attr(test, test)]
    fn natural_key_ignores_leading_zeros_like_int() {
        assert_eq!(natural_sort_key("a007b"), natural_sort_key("a7b"));
        assert!(natural_sort_key("a7b") < natural_sort_key("a08b"));
    }

    #[cfg_attr(test, test)]
    fn natural_key_is_unbounded() {
        // Python's int() has no width limit; a u64/i64 parse would overflow.
        let big = "9".repeat(40);
        let bigger = format!("{}0", big);
        assert!(natural_sort_key(&big) < natural_sort_key(&bigger));
    }

    #[cfg_attr(test, test)]
    fn py_lower_has_no_final_sigma_rule() {
        // str::to_lowercase would give "ας" for this.
        assert_eq!(py_lower("ΑΣ"), "ασ");
    }

    #[cfg_attr(test, test)]
    fn insertion_map_iterates_in_insertion_order() {
        let mut m: InsertionMap<i32> = InsertionMap::new();
        m.insert("z".into(), 1);
        m.insert("a".into(), 2);
        m.insert("m".into(), 3);
        m.insert("z".into(), 9); // overwrite keeps position
        assert_eq!(m.keys(), &["z".to_string(), "a".into(), "m".into()]);
        assert_eq!(m.into_values(), vec![9, 2, 3]);
    }

    fn sample() -> DsnExporterInputs {
        DsnExporterInputs {
            board: ExpBoard {
                width: 100.0,
                height: 80.0,
                keepouts: vec![],
                layers: None,
            },
            components: vec![],
            nets: vec![],
            positions: None,
            rotation_indices: None,
            deterministic: true,
            pin_world_positions: None,
        }
    }

    #[cfg_attr(test, test)]
    fn structure_matches_the_pinned_shape() {
        let core = DsnExporterCore::new(sample());
        let out = crate::dsn_types::dsn_expression_to_string(&core.export_structure(true));
        assert!(out.contains("(layer F.Cu (type signal) (property (index 0)))"));
        assert!(out.contains("(boundary (rect pcb 0 0 10000 8000))"));
        assert!(out.contains("(via VIA)"));
        assert!(out.contains("(rule (width 13) (clearance 12))"));
    }

    #[cfg_attr(test, test)]
    fn keepout_sort_is_string_not_numeric() {
        let mut inputs = sample();
        inputs.board.keepouts = (0..12).map(|i| (i as f64, 1.0, 2.0, 3.0)).collect();
        let core = DsnExporterCore::new(inputs);
        let out = crate::dsn_types::dsn_expression_to_string(&core.export_structure(true));
        // `str(k.args[0])` sorts KO_10 and KO_11 before KO_2.
        let pos10 = out.find("KO_10").unwrap();
        let pos2 = out.find("KO_2").unwrap();
        assert!(pos10 < pos2);
    }

    #[cfg_attr(test, test)]
    fn pcb_carries_schema_comment_only_when_deterministic() {
        let core = DsnExporterCore::new(sample());
        let out = crate::dsn_types::dsn_expression_to_string(&core.export_pcb(
            "t",
            None,
            None,
            Some("abc"),
        ));
        assert!(out.starts_with(";schema-version: sha256:abc\n"));

        let mut nd = sample();
        nd.deterministic = false;
        let core = DsnExporterCore::new(nd);
        let out = crate::dsn_types::dsn_expression_to_string(&core.export_pcb(
            "t",
            None,
            None,
            Some("abc"),
        ));
        assert!(!out.starts_with(';'));
    }

    #[cfg_attr(test, test)]
    fn empty_trace_list_emits_no_wiring_section() {
        let core = DsnExporterCore::new(sample());
        let out =
            crate::dsn_types::dsn_expression_to_string(&core.export_pcb("t", Some(&[]), None, None));
        assert!(!out.contains("(wiring"));
    }

    #[cfg_attr(test, test)]
    fn voltage_pattern_matches_python_dollar_before_trailing_newline() {
        assert!(DsnExporterCore::voltage_pattern().is_match("VCC3V3"));
        assert!(DsnExporterCore::voltage_pattern().is_match("vcc3v3"));
        // Python's `$` matches before a trailing newline; `\z` would not.
        assert!(DsnExporterCore::voltage_pattern().is_match("VCC3V3\n"));
        assert!(!DsnExporterCore::voltage_pattern().is_match("SIG1"));
    }

    // -- py_repr_float ---------------------------------------------------

    #[cfg_attr(test, test)]
    fn py_repr_float_special_values_match_cpython() {
        assert_eq!(py_repr_float(f64::NAN), "nan");
        assert_eq!(py_repr_float(f64::INFINITY), "inf");
        assert_eq!(py_repr_float(f64::NEG_INFINITY), "-inf");
        assert_eq!(py_repr_float(0.0), "0.0");
        assert_eq!(py_repr_float(-0.0), "-0.0");
    }

    #[cfg_attr(test, test)]
    fn py_repr_float_small_integer_valued() {
        assert_eq!(py_repr_float(1.0), "1.0");
        assert_eq!(py_repr_float(42.0), "42.0");
        assert_eq!(py_repr_float(0.5), "0.5");
    }

    /// B10-class BUG (fixed 2026-08-10): `py_repr_float` used to be a local
    /// Rust Display (`{}`) implementation.  Display's fixed-point /
    /// scientific cutoffs differ from CPython's `repr(float)`, and neither
    /// the `+` sign nor the zero-padding is applied.  This produced wrong
    /// strings for values that cross CPython's `1e16` and `1e-4` thresholds
    /// and for any value where the shortest representation is scientific.
    ///
    /// Counter-examples (the values that were wrong):
    /// - 1e-5  → got "0.00001", expected "1e-05"
    /// - 1e16  → got "10000000000000000.0", expected "1e+16"
    /// - 1e300 → got a 301-char fixed-point string, expected "1e+300"
    ///
    /// The function now delegates to `py_float_str` (the empirically-verified
    /// CPython `repr(float)` replica), so the values below MUST match CPython
    /// 3.12 exactly.  They are asserted positively — a regression back to
    /// the Display path fails here.
    ///
    /// Mitigation context: the function is only reachable from sort-key
    /// lambdas, and no DSN argument that carries a `float` currently appears
    /// in a sorted position, so the bug was latent — it would only have
    /// affected export ordering if a float ever landed in a sorted slot.
    #[cfg_attr(test, test)]
    fn py_repr_float_b10_matches_cpython() {
        // These must now match CPython repr(float) exactly.
        let got_neg5 = py_repr_float(1e-5);
        assert_eq!(got_neg5, "1e-05", "py_repr_float(1e-5) = '{got_neg5}'");
        let got_16 = py_repr_float(1e16);
        assert_eq!(got_16, "1e+16", "py_repr_float(1e16) = '{got_16}'");
        let got_300 = py_repr_float(1e300);
        assert_eq!(got_300, "1e+300", "py_repr_float(1e300) = '{got_300}'");
        // Fixed-point threshold values stay fixed (CPython repr switches to
        // scientific only at 1e16 / 1e-5).
        assert_eq!(py_repr_float(1e15), "1000000000000000.0");
        assert_eq!(py_repr_float(999999999999999.0), "999999999999999.0");
        assert_eq!(py_repr_float(1e-4), "0.0001");
        // B10 exponent zero-padding: the exponent must be two digits.
        assert!(py_repr_float(1e-5).contains("e-05"));
        // Special values still round-trip.
        assert_eq!(py_repr_float(f64::NAN), "nan");
        assert_eq!(py_repr_float(f64::INFINITY), "inf");
        assert_eq!(py_repr_float(f64::NEG_INFINITY), "-inf");
        assert_eq!(py_repr_float(0.0), "0.0");
        assert_eq!(py_repr_float(-0.0), "-0.0");
        assert_eq!(py_repr_float(42.0), "42.0");
    }

    #[cfg_attr(test, test)]
    fn natural_sort_key_empty_text_trailing() {
        // The trailing empty Text from `re.split` should sort before any
        // non-empty text: "a" < "a0" because "" < "0" in the trailing
        // position.
        let ka = natural_sort_key("a");
        let kb = natural_sort_key("a0");
        assert!(ka < kb, "natural_sort_key(\"a\") should be < natural_sort_key(\"a0\")");
    }

    #[cfg_attr(test, test)]
    fn natural_sort_key_all_zeros_digit_run() {
        // "a000b" should key exactly like "a0b" (int("000") == int("0") == 0)
        assert_eq!(natural_sort_key("a000b"), natural_sort_key("a0b"));
    }

    #[cfg_attr(test, test)]
    fn py_format_fixed_negative_zero() {
        // format!("{:.3}", -0.0) in Rust produces "-0.000"
        assert_eq!(py_format_fixed(-0.0, 3), "-0.000");
        assert_eq!(py_format_fixed(0.0, 2), "0.00");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("dsn_exporter::tests::round_is_half_to_even_not_half_away", round_is_half_to_even_not_half_away),
        ("dsn_exporter::tests::natural_key_orders_numerically_not_lexically", natural_key_orders_numerically_not_lexically),
        ("dsn_exporter::tests::natural_key_ignores_leading_zeros_like_int", natural_key_ignores_leading_zeros_like_int),
        ("dsn_exporter::tests::natural_key_is_unbounded", natural_key_is_unbounded),
        ("dsn_exporter::tests::py_lower_has_no_final_sigma_rule", py_lower_has_no_final_sigma_rule),
        ("dsn_exporter::tests::insertion_map_iterates_in_insertion_order", insertion_map_iterates_in_insertion_order),
        ("dsn_exporter::tests::structure_matches_the_pinned_shape", structure_matches_the_pinned_shape),
        ("dsn_exporter::tests::keepout_sort_is_string_not_numeric", keepout_sort_is_string_not_numeric),
        ("dsn_exporter::tests::pcb_carries_schema_comment_only_when_deterministic", pcb_carries_schema_comment_only_when_deterministic),
        ("dsn_exporter::tests::empty_trace_list_emits_no_wiring_section", empty_trace_list_emits_no_wiring_section),
        ("dsn_exporter::tests::voltage_pattern_matches_python_dollar_before_trailing_newline", voltage_pattern_matches_python_dollar_before_trailing_newline),
        ("dsn_exporter::tests::py_repr_float_special_values_match_cpython", py_repr_float_special_values_match_cpython),
        ("dsn_exporter::tests::py_repr_float_small_integer_valued", py_repr_float_small_integer_valued),
        ("dsn_exporter::tests::py_repr_float_b10_matches_cpython", py_repr_float_b10_matches_cpython),
        ("dsn_exporter::tests::natural_sort_key_empty_text_trailing", natural_sort_key_empty_text_trailing),
        ("dsn_exporter::tests::natural_sort_key_all_zeros_digit_run", natural_sort_key_all_zeros_digit_run),
        ("dsn_exporter::tests::py_format_fixed_negative_zero", py_format_fixed_negative_zero),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}


// ---------------------------------------------------------------------------
// Deterministic property campaigns (no `proptest`) -- mirrors this file's
// own `proptests` module (excluded from the wasm build: `proptest` is a
// dev-dependency) with fixed-seed cases over the same three private
// kernels (`py_round_half_even`, `natural_sort_key`, `py_format_fixed`).
// A nested module (ident `property_campaigns`, distinct from this file's
// existing `tests` module -- reusing that ident here would collide in the
// registry generator's flat `(file, ident)` keying) rather than a
// crate-root sibling, because those kernels are module-private `fn`s --
// only a descendant of THIS module can name them (Rust privacy), matching
// `dag_expr::depth_boundary`'s precedent for a per-file generated-campaign
// submodule elsewhere in this crate.
//
// Self-contained SplitMix64 PRNG, duplicated rather than shared with
// `crate::property_campaigns` (whose `SplitMix64` is private to that
// module) -- the same duplication that module's own doc comment describes
// relative to `temper-geometry`'s.  Zero external imports: no `proptest`,
// no `rand`, no clock, no OS entropy.
//
// Written in plain `#[cfg(test)]` / `#[test]` form (not the post-generation
// `wasm-registry` gate / `#[cfg_attr(test, test)]` form other modules in
// this crate already show) -- `scripts/gen_wasm_test_registry.py` rewrites
// both and appends the `WASM_TESTS` const on the next regeneration, exactly
// as it did the first time for every other module.
// ---------------------------------------------------------------------------
#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod property_campaigns {
    use super::*;

    struct SplitMix64(u64);

    impl SplitMix64 {
        fn new(seed: u64) -> Self {
            Self(seed)
        }

        fn next_u64(&mut self) -> u64 {
            self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = self.0;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        }

        fn next_f64(&mut self) -> f64 {
            (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
        }

        fn range(&mut self, lo: f64, hi: f64) -> f64 {
            lo + self.next_f64() * (hi - lo)
        }

        fn index(&mut self, n: usize) -> usize {
            (self.next_u64() % n as u64) as usize
        }
    }

    fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
        SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
    }

    fn de_gen_normal(seed: u64, salt: u64) -> f64 {
        sub_rng(seed, salt).range(-1e6, 1e6)
    }

    const DE_ALNUM: &[u8] = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

    fn de_gen_alnum_string(rng: &mut SplitMix64, max_len: usize) -> String {
        let len = rng.index(max_len + 1);
        (0..len).map(|_| DE_ALNUM[rng.index(DE_ALNUM.len())] as char).collect()
    }

    /// p: `py_round_half_even`'s integer result is within 0.5 (plus a tiny
    /// float slop) of the original value -- the reversibility bound every
    /// correct rounding function must satisfy.
    pub(crate) fn de_round_half_even_round_trips_sign_impl(seed: u64) {
        let x = de_gen_normal(seed, 1);
        let r = py_round_half_even(x);
        let diff = (r as f64 - x).abs();
        assert!(diff <= 0.5 + 1e-12, "seed={seed} x={x} r={r} diff={diff}");
    }

    /// p: `py_round_half_even` is idempotent -- rounding an already-integral
    /// value is a no-op.
    pub(crate) fn de_round_half_even_idempotent_impl(seed: u64) {
        let x = de_gen_normal(seed, 1);
        let r = py_round_half_even(x);
        assert_eq!(py_round_half_even(r as f64), r, "seed={seed} x={x} r={r}");
    }

    /// p: `natural_sort_key` induces a transitive order over generated
    /// alphanumeric strings.
    pub(crate) fn de_natural_sort_key_total_order_impl(seed: u64) {
        let a = de_gen_alnum_string(&mut sub_rng(seed, 1), 20);
        let b = de_gen_alnum_string(&mut sub_rng(seed, 2), 20);
        let c = de_gen_alnum_string(&mut sub_rng(seed, 3), 20);
        let ka = natural_sort_key(&a);
        let kb = natural_sort_key(&b);
        let kc = natural_sort_key(&c);
        if ka <= kb && kb <= kc {
            assert!(ka <= kc, "seed={seed} a={a:?} b={b:?} c={c:?} transitivity violated");
        }
    }

    /// p: `py_format_fixed(x, prec)` renders exactly `prec` digits after the
    /// decimal point for a finite `x` and `prec > 0`.
    pub(crate) fn de_format_fixed_round_trips_precision_impl(seed: u64) {
        let x = de_gen_normal(seed, 1);
        let prec = sub_rng(seed, 2).index(6); // 0..=5
        let s = py_format_fixed(x, prec);
        if x.is_finite() && prec > 0 {
            assert!(s.contains('.'), "seed={seed} prec={prec} x={x} produced no decimal: {s:?}");
            let after_dot = match s.split('.').nth(1) {
                Some(a) => a,
                None => panic!("seed={seed} s={s:?} claims '.' but split('.') has no second part"),
            };
            assert_eq!(after_dot.len(), prec, "seed={seed} prec={prec} x={x} s={s:?}");
        }
    }


    // --- de_round_half_even_round_trips_sign: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000000() { de_round_half_even_round_trips_sign_impl(0); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000001() { de_round_half_even_round_trips_sign_impl(1); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000002() { de_round_half_even_round_trips_sign_impl(2); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000003() { de_round_half_even_round_trips_sign_impl(3); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000004() { de_round_half_even_round_trips_sign_impl(4); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000005() { de_round_half_even_round_trips_sign_impl(5); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000006() { de_round_half_even_round_trips_sign_impl(6); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000007() { de_round_half_even_round_trips_sign_impl(7); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000008() { de_round_half_even_round_trips_sign_impl(8); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000009() { de_round_half_even_round_trips_sign_impl(9); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000010() { de_round_half_even_round_trips_sign_impl(10); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000011() { de_round_half_even_round_trips_sign_impl(11); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000012() { de_round_half_even_round_trips_sign_impl(12); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000013() { de_round_half_even_round_trips_sign_impl(13); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000014() { de_round_half_even_round_trips_sign_impl(14); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000015() { de_round_half_even_round_trips_sign_impl(15); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000016() { de_round_half_even_round_trips_sign_impl(16); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000017() { de_round_half_even_round_trips_sign_impl(17); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000018() { de_round_half_even_round_trips_sign_impl(18); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000019() { de_round_half_even_round_trips_sign_impl(19); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000020() { de_round_half_even_round_trips_sign_impl(20); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000021() { de_round_half_even_round_trips_sign_impl(21); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000022() { de_round_half_even_round_trips_sign_impl(22); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000023() { de_round_half_even_round_trips_sign_impl(23); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000024() { de_round_half_even_round_trips_sign_impl(24); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000025() { de_round_half_even_round_trips_sign_impl(25); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000026() { de_round_half_even_round_trips_sign_impl(26); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000027() { de_round_half_even_round_trips_sign_impl(27); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000028() { de_round_half_even_round_trips_sign_impl(28); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000029() { de_round_half_even_round_trips_sign_impl(29); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000030() { de_round_half_even_round_trips_sign_impl(30); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000031() { de_round_half_even_round_trips_sign_impl(31); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000032() { de_round_half_even_round_trips_sign_impl(32); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000033() { de_round_half_even_round_trips_sign_impl(33); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000034() { de_round_half_even_round_trips_sign_impl(34); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000035() { de_round_half_even_round_trips_sign_impl(35); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000036() { de_round_half_even_round_trips_sign_impl(36); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000037() { de_round_half_even_round_trips_sign_impl(37); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000038() { de_round_half_even_round_trips_sign_impl(38); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000039() { de_round_half_even_round_trips_sign_impl(39); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000040() { de_round_half_even_round_trips_sign_impl(40); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000041() { de_round_half_even_round_trips_sign_impl(41); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000042() { de_round_half_even_round_trips_sign_impl(42); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000043() { de_round_half_even_round_trips_sign_impl(43); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000044() { de_round_half_even_round_trips_sign_impl(44); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000045() { de_round_half_even_round_trips_sign_impl(45); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000046() { de_round_half_even_round_trips_sign_impl(46); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000047() { de_round_half_even_round_trips_sign_impl(47); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000048() { de_round_half_even_round_trips_sign_impl(48); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000049() { de_round_half_even_round_trips_sign_impl(49); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000050() { de_round_half_even_round_trips_sign_impl(50); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000051() { de_round_half_even_round_trips_sign_impl(51); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000052() { de_round_half_even_round_trips_sign_impl(52); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000053() { de_round_half_even_round_trips_sign_impl(53); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000054() { de_round_half_even_round_trips_sign_impl(54); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000055() { de_round_half_even_round_trips_sign_impl(55); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000056() { de_round_half_even_round_trips_sign_impl(56); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000057() { de_round_half_even_round_trips_sign_impl(57); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000058() { de_round_half_even_round_trips_sign_impl(58); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000059() { de_round_half_even_round_trips_sign_impl(59); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000060() { de_round_half_even_round_trips_sign_impl(60); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000061() { de_round_half_even_round_trips_sign_impl(61); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000062() { de_round_half_even_round_trips_sign_impl(62); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000063() { de_round_half_even_round_trips_sign_impl(63); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000064() { de_round_half_even_round_trips_sign_impl(64); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000065() { de_round_half_even_round_trips_sign_impl(65); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000066() { de_round_half_even_round_trips_sign_impl(66); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000067() { de_round_half_even_round_trips_sign_impl(67); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000068() { de_round_half_even_round_trips_sign_impl(68); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000069() { de_round_half_even_round_trips_sign_impl(69); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000070() { de_round_half_even_round_trips_sign_impl(70); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000071() { de_round_half_even_round_trips_sign_impl(71); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000072() { de_round_half_even_round_trips_sign_impl(72); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000073() { de_round_half_even_round_trips_sign_impl(73); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000074() { de_round_half_even_round_trips_sign_impl(74); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000075() { de_round_half_even_round_trips_sign_impl(75); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000076() { de_round_half_even_round_trips_sign_impl(76); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000077() { de_round_half_even_round_trips_sign_impl(77); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000078() { de_round_half_even_round_trips_sign_impl(78); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000079() { de_round_half_even_round_trips_sign_impl(79); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000080() { de_round_half_even_round_trips_sign_impl(80); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000081() { de_round_half_even_round_trips_sign_impl(81); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000082() { de_round_half_even_round_trips_sign_impl(82); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000083() { de_round_half_even_round_trips_sign_impl(83); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000084() { de_round_half_even_round_trips_sign_impl(84); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000085() { de_round_half_even_round_trips_sign_impl(85); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000086() { de_round_half_even_round_trips_sign_impl(86); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000087() { de_round_half_even_round_trips_sign_impl(87); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000088() { de_round_half_even_round_trips_sign_impl(88); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000089() { de_round_half_even_round_trips_sign_impl(89); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000090() { de_round_half_even_round_trips_sign_impl(90); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000091() { de_round_half_even_round_trips_sign_impl(91); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000092() { de_round_half_even_round_trips_sign_impl(92); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000093() { de_round_half_even_round_trips_sign_impl(93); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000094() { de_round_half_even_round_trips_sign_impl(94); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000095() { de_round_half_even_round_trips_sign_impl(95); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000096() { de_round_half_even_round_trips_sign_impl(96); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000097() { de_round_half_even_round_trips_sign_impl(97); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000098() { de_round_half_even_round_trips_sign_impl(98); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_round_trips_sign_seed_000099() { de_round_half_even_round_trips_sign_impl(99); }
    // --- de_round_half_even_idempotent: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000000() { de_round_half_even_idempotent_impl(0); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000001() { de_round_half_even_idempotent_impl(1); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000002() { de_round_half_even_idempotent_impl(2); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000003() { de_round_half_even_idempotent_impl(3); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000004() { de_round_half_even_idempotent_impl(4); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000005() { de_round_half_even_idempotent_impl(5); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000006() { de_round_half_even_idempotent_impl(6); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000007() { de_round_half_even_idempotent_impl(7); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000008() { de_round_half_even_idempotent_impl(8); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000009() { de_round_half_even_idempotent_impl(9); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000010() { de_round_half_even_idempotent_impl(10); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000011() { de_round_half_even_idempotent_impl(11); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000012() { de_round_half_even_idempotent_impl(12); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000013() { de_round_half_even_idempotent_impl(13); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000014() { de_round_half_even_idempotent_impl(14); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000015() { de_round_half_even_idempotent_impl(15); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000016() { de_round_half_even_idempotent_impl(16); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000017() { de_round_half_even_idempotent_impl(17); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000018() { de_round_half_even_idempotent_impl(18); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000019() { de_round_half_even_idempotent_impl(19); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000020() { de_round_half_even_idempotent_impl(20); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000021() { de_round_half_even_idempotent_impl(21); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000022() { de_round_half_even_idempotent_impl(22); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000023() { de_round_half_even_idempotent_impl(23); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000024() { de_round_half_even_idempotent_impl(24); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000025() { de_round_half_even_idempotent_impl(25); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000026() { de_round_half_even_idempotent_impl(26); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000027() { de_round_half_even_idempotent_impl(27); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000028() { de_round_half_even_idempotent_impl(28); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000029() { de_round_half_even_idempotent_impl(29); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000030() { de_round_half_even_idempotent_impl(30); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000031() { de_round_half_even_idempotent_impl(31); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000032() { de_round_half_even_idempotent_impl(32); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000033() { de_round_half_even_idempotent_impl(33); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000034() { de_round_half_even_idempotent_impl(34); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000035() { de_round_half_even_idempotent_impl(35); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000036() { de_round_half_even_idempotent_impl(36); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000037() { de_round_half_even_idempotent_impl(37); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000038() { de_round_half_even_idempotent_impl(38); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000039() { de_round_half_even_idempotent_impl(39); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000040() { de_round_half_even_idempotent_impl(40); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000041() { de_round_half_even_idempotent_impl(41); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000042() { de_round_half_even_idempotent_impl(42); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000043() { de_round_half_even_idempotent_impl(43); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000044() { de_round_half_even_idempotent_impl(44); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000045() { de_round_half_even_idempotent_impl(45); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000046() { de_round_half_even_idempotent_impl(46); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000047() { de_round_half_even_idempotent_impl(47); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000048() { de_round_half_even_idempotent_impl(48); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000049() { de_round_half_even_idempotent_impl(49); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000050() { de_round_half_even_idempotent_impl(50); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000051() { de_round_half_even_idempotent_impl(51); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000052() { de_round_half_even_idempotent_impl(52); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000053() { de_round_half_even_idempotent_impl(53); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000054() { de_round_half_even_idempotent_impl(54); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000055() { de_round_half_even_idempotent_impl(55); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000056() { de_round_half_even_idempotent_impl(56); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000057() { de_round_half_even_idempotent_impl(57); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000058() { de_round_half_even_idempotent_impl(58); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000059() { de_round_half_even_idempotent_impl(59); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000060() { de_round_half_even_idempotent_impl(60); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000061() { de_round_half_even_idempotent_impl(61); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000062() { de_round_half_even_idempotent_impl(62); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000063() { de_round_half_even_idempotent_impl(63); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000064() { de_round_half_even_idempotent_impl(64); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000065() { de_round_half_even_idempotent_impl(65); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000066() { de_round_half_even_idempotent_impl(66); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000067() { de_round_half_even_idempotent_impl(67); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000068() { de_round_half_even_idempotent_impl(68); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000069() { de_round_half_even_idempotent_impl(69); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000070() { de_round_half_even_idempotent_impl(70); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000071() { de_round_half_even_idempotent_impl(71); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000072() { de_round_half_even_idempotent_impl(72); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000073() { de_round_half_even_idempotent_impl(73); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000074() { de_round_half_even_idempotent_impl(74); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000075() { de_round_half_even_idempotent_impl(75); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000076() { de_round_half_even_idempotent_impl(76); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000077() { de_round_half_even_idempotent_impl(77); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000078() { de_round_half_even_idempotent_impl(78); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000079() { de_round_half_even_idempotent_impl(79); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000080() { de_round_half_even_idempotent_impl(80); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000081() { de_round_half_even_idempotent_impl(81); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000082() { de_round_half_even_idempotent_impl(82); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000083() { de_round_half_even_idempotent_impl(83); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000084() { de_round_half_even_idempotent_impl(84); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000085() { de_round_half_even_idempotent_impl(85); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000086() { de_round_half_even_idempotent_impl(86); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000087() { de_round_half_even_idempotent_impl(87); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000088() { de_round_half_even_idempotent_impl(88); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000089() { de_round_half_even_idempotent_impl(89); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000090() { de_round_half_even_idempotent_impl(90); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000091() { de_round_half_even_idempotent_impl(91); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000092() { de_round_half_even_idempotent_impl(92); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000093() { de_round_half_even_idempotent_impl(93); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000094() { de_round_half_even_idempotent_impl(94); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000095() { de_round_half_even_idempotent_impl(95); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000096() { de_round_half_even_idempotent_impl(96); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000097() { de_round_half_even_idempotent_impl(97); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000098() { de_round_half_even_idempotent_impl(98); }
    #[cfg_attr(test, test)]
    fn de_round_half_even_idempotent_seed_000099() { de_round_half_even_idempotent_impl(99); }
    // --- de_natural_sort_key_total_order: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000000() { de_natural_sort_key_total_order_impl(0); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000001() { de_natural_sort_key_total_order_impl(1); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000002() { de_natural_sort_key_total_order_impl(2); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000003() { de_natural_sort_key_total_order_impl(3); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000004() { de_natural_sort_key_total_order_impl(4); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000005() { de_natural_sort_key_total_order_impl(5); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000006() { de_natural_sort_key_total_order_impl(6); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000007() { de_natural_sort_key_total_order_impl(7); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000008() { de_natural_sort_key_total_order_impl(8); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000009() { de_natural_sort_key_total_order_impl(9); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000010() { de_natural_sort_key_total_order_impl(10); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000011() { de_natural_sort_key_total_order_impl(11); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000012() { de_natural_sort_key_total_order_impl(12); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000013() { de_natural_sort_key_total_order_impl(13); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000014() { de_natural_sort_key_total_order_impl(14); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000015() { de_natural_sort_key_total_order_impl(15); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000016() { de_natural_sort_key_total_order_impl(16); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000017() { de_natural_sort_key_total_order_impl(17); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000018() { de_natural_sort_key_total_order_impl(18); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000019() { de_natural_sort_key_total_order_impl(19); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000020() { de_natural_sort_key_total_order_impl(20); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000021() { de_natural_sort_key_total_order_impl(21); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000022() { de_natural_sort_key_total_order_impl(22); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000023() { de_natural_sort_key_total_order_impl(23); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000024() { de_natural_sort_key_total_order_impl(24); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000025() { de_natural_sort_key_total_order_impl(25); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000026() { de_natural_sort_key_total_order_impl(26); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000027() { de_natural_sort_key_total_order_impl(27); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000028() { de_natural_sort_key_total_order_impl(28); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000029() { de_natural_sort_key_total_order_impl(29); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000030() { de_natural_sort_key_total_order_impl(30); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000031() { de_natural_sort_key_total_order_impl(31); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000032() { de_natural_sort_key_total_order_impl(32); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000033() { de_natural_sort_key_total_order_impl(33); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000034() { de_natural_sort_key_total_order_impl(34); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000035() { de_natural_sort_key_total_order_impl(35); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000036() { de_natural_sort_key_total_order_impl(36); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000037() { de_natural_sort_key_total_order_impl(37); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000038() { de_natural_sort_key_total_order_impl(38); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000039() { de_natural_sort_key_total_order_impl(39); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000040() { de_natural_sort_key_total_order_impl(40); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000041() { de_natural_sort_key_total_order_impl(41); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000042() { de_natural_sort_key_total_order_impl(42); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000043() { de_natural_sort_key_total_order_impl(43); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000044() { de_natural_sort_key_total_order_impl(44); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000045() { de_natural_sort_key_total_order_impl(45); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000046() { de_natural_sort_key_total_order_impl(46); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000047() { de_natural_sort_key_total_order_impl(47); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000048() { de_natural_sort_key_total_order_impl(48); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000049() { de_natural_sort_key_total_order_impl(49); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000050() { de_natural_sort_key_total_order_impl(50); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000051() { de_natural_sort_key_total_order_impl(51); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000052() { de_natural_sort_key_total_order_impl(52); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000053() { de_natural_sort_key_total_order_impl(53); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000054() { de_natural_sort_key_total_order_impl(54); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000055() { de_natural_sort_key_total_order_impl(55); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000056() { de_natural_sort_key_total_order_impl(56); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000057() { de_natural_sort_key_total_order_impl(57); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000058() { de_natural_sort_key_total_order_impl(58); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000059() { de_natural_sort_key_total_order_impl(59); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000060() { de_natural_sort_key_total_order_impl(60); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000061() { de_natural_sort_key_total_order_impl(61); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000062() { de_natural_sort_key_total_order_impl(62); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000063() { de_natural_sort_key_total_order_impl(63); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000064() { de_natural_sort_key_total_order_impl(64); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000065() { de_natural_sort_key_total_order_impl(65); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000066() { de_natural_sort_key_total_order_impl(66); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000067() { de_natural_sort_key_total_order_impl(67); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000068() { de_natural_sort_key_total_order_impl(68); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000069() { de_natural_sort_key_total_order_impl(69); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000070() { de_natural_sort_key_total_order_impl(70); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000071() { de_natural_sort_key_total_order_impl(71); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000072() { de_natural_sort_key_total_order_impl(72); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000073() { de_natural_sort_key_total_order_impl(73); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000074() { de_natural_sort_key_total_order_impl(74); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000075() { de_natural_sort_key_total_order_impl(75); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000076() { de_natural_sort_key_total_order_impl(76); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000077() { de_natural_sort_key_total_order_impl(77); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000078() { de_natural_sort_key_total_order_impl(78); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000079() { de_natural_sort_key_total_order_impl(79); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000080() { de_natural_sort_key_total_order_impl(80); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000081() { de_natural_sort_key_total_order_impl(81); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000082() { de_natural_sort_key_total_order_impl(82); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000083() { de_natural_sort_key_total_order_impl(83); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000084() { de_natural_sort_key_total_order_impl(84); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000085() { de_natural_sort_key_total_order_impl(85); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000086() { de_natural_sort_key_total_order_impl(86); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000087() { de_natural_sort_key_total_order_impl(87); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000088() { de_natural_sort_key_total_order_impl(88); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000089() { de_natural_sort_key_total_order_impl(89); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000090() { de_natural_sort_key_total_order_impl(90); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000091() { de_natural_sort_key_total_order_impl(91); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000092() { de_natural_sort_key_total_order_impl(92); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000093() { de_natural_sort_key_total_order_impl(93); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000094() { de_natural_sort_key_total_order_impl(94); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000095() { de_natural_sort_key_total_order_impl(95); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000096() { de_natural_sort_key_total_order_impl(96); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000097() { de_natural_sort_key_total_order_impl(97); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000098() { de_natural_sort_key_total_order_impl(98); }
    #[cfg_attr(test, test)]
    fn de_natural_sort_key_total_order_seed_000099() { de_natural_sort_key_total_order_impl(99); }
    // --- de_format_fixed_round_trips_precision: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000000() { de_format_fixed_round_trips_precision_impl(0); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000001() { de_format_fixed_round_trips_precision_impl(1); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000002() { de_format_fixed_round_trips_precision_impl(2); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000003() { de_format_fixed_round_trips_precision_impl(3); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000004() { de_format_fixed_round_trips_precision_impl(4); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000005() { de_format_fixed_round_trips_precision_impl(5); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000006() { de_format_fixed_round_trips_precision_impl(6); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000007() { de_format_fixed_round_trips_precision_impl(7); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000008() { de_format_fixed_round_trips_precision_impl(8); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000009() { de_format_fixed_round_trips_precision_impl(9); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000010() { de_format_fixed_round_trips_precision_impl(10); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000011() { de_format_fixed_round_trips_precision_impl(11); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000012() { de_format_fixed_round_trips_precision_impl(12); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000013() { de_format_fixed_round_trips_precision_impl(13); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000014() { de_format_fixed_round_trips_precision_impl(14); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000015() { de_format_fixed_round_trips_precision_impl(15); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000016() { de_format_fixed_round_trips_precision_impl(16); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000017() { de_format_fixed_round_trips_precision_impl(17); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000018() { de_format_fixed_round_trips_precision_impl(18); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000019() { de_format_fixed_round_trips_precision_impl(19); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000020() { de_format_fixed_round_trips_precision_impl(20); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000021() { de_format_fixed_round_trips_precision_impl(21); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000022() { de_format_fixed_round_trips_precision_impl(22); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000023() { de_format_fixed_round_trips_precision_impl(23); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000024() { de_format_fixed_round_trips_precision_impl(24); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000025() { de_format_fixed_round_trips_precision_impl(25); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000026() { de_format_fixed_round_trips_precision_impl(26); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000027() { de_format_fixed_round_trips_precision_impl(27); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000028() { de_format_fixed_round_trips_precision_impl(28); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000029() { de_format_fixed_round_trips_precision_impl(29); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000030() { de_format_fixed_round_trips_precision_impl(30); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000031() { de_format_fixed_round_trips_precision_impl(31); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000032() { de_format_fixed_round_trips_precision_impl(32); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000033() { de_format_fixed_round_trips_precision_impl(33); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000034() { de_format_fixed_round_trips_precision_impl(34); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000035() { de_format_fixed_round_trips_precision_impl(35); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000036() { de_format_fixed_round_trips_precision_impl(36); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000037() { de_format_fixed_round_trips_precision_impl(37); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000038() { de_format_fixed_round_trips_precision_impl(38); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000039() { de_format_fixed_round_trips_precision_impl(39); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000040() { de_format_fixed_round_trips_precision_impl(40); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000041() { de_format_fixed_round_trips_precision_impl(41); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000042() { de_format_fixed_round_trips_precision_impl(42); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000043() { de_format_fixed_round_trips_precision_impl(43); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000044() { de_format_fixed_round_trips_precision_impl(44); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000045() { de_format_fixed_round_trips_precision_impl(45); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000046() { de_format_fixed_round_trips_precision_impl(46); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000047() { de_format_fixed_round_trips_precision_impl(47); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000048() { de_format_fixed_round_trips_precision_impl(48); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000049() { de_format_fixed_round_trips_precision_impl(49); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000050() { de_format_fixed_round_trips_precision_impl(50); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000051() { de_format_fixed_round_trips_precision_impl(51); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000052() { de_format_fixed_round_trips_precision_impl(52); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000053() { de_format_fixed_round_trips_precision_impl(53); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000054() { de_format_fixed_round_trips_precision_impl(54); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000055() { de_format_fixed_round_trips_precision_impl(55); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000056() { de_format_fixed_round_trips_precision_impl(56); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000057() { de_format_fixed_round_trips_precision_impl(57); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000058() { de_format_fixed_round_trips_precision_impl(58); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000059() { de_format_fixed_round_trips_precision_impl(59); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000060() { de_format_fixed_round_trips_precision_impl(60); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000061() { de_format_fixed_round_trips_precision_impl(61); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000062() { de_format_fixed_round_trips_precision_impl(62); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000063() { de_format_fixed_round_trips_precision_impl(63); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000064() { de_format_fixed_round_trips_precision_impl(64); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000065() { de_format_fixed_round_trips_precision_impl(65); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000066() { de_format_fixed_round_trips_precision_impl(66); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000067() { de_format_fixed_round_trips_precision_impl(67); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000068() { de_format_fixed_round_trips_precision_impl(68); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000069() { de_format_fixed_round_trips_precision_impl(69); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000070() { de_format_fixed_round_trips_precision_impl(70); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000071() { de_format_fixed_round_trips_precision_impl(71); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000072() { de_format_fixed_round_trips_precision_impl(72); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000073() { de_format_fixed_round_trips_precision_impl(73); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000074() { de_format_fixed_round_trips_precision_impl(74); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000075() { de_format_fixed_round_trips_precision_impl(75); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000076() { de_format_fixed_round_trips_precision_impl(76); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000077() { de_format_fixed_round_trips_precision_impl(77); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000078() { de_format_fixed_round_trips_precision_impl(78); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000079() { de_format_fixed_round_trips_precision_impl(79); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000080() { de_format_fixed_round_trips_precision_impl(80); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000081() { de_format_fixed_round_trips_precision_impl(81); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000082() { de_format_fixed_round_trips_precision_impl(82); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000083() { de_format_fixed_round_trips_precision_impl(83); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000084() { de_format_fixed_round_trips_precision_impl(84); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000085() { de_format_fixed_round_trips_precision_impl(85); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000086() { de_format_fixed_round_trips_precision_impl(86); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000087() { de_format_fixed_round_trips_precision_impl(87); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000088() { de_format_fixed_round_trips_precision_impl(88); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000089() { de_format_fixed_round_trips_precision_impl(89); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000090() { de_format_fixed_round_trips_precision_impl(90); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000091() { de_format_fixed_round_trips_precision_impl(91); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000092() { de_format_fixed_round_trips_precision_impl(92); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000093() { de_format_fixed_round_trips_precision_impl(93); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000094() { de_format_fixed_round_trips_precision_impl(94); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000095() { de_format_fixed_round_trips_precision_impl(95); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000096() { de_format_fixed_round_trips_precision_impl(96); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000097() { de_format_fixed_round_trips_precision_impl(97); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000098() { de_format_fixed_round_trips_precision_impl(98); }
    #[cfg_attr(test, test)]
    fn de_format_fixed_round_trips_precision_seed_000099() { de_format_fixed_round_trips_precision_impl(99); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: property_campaigns ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000000", de_round_half_even_round_trips_sign_seed_000000),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000001", de_round_half_even_round_trips_sign_seed_000001),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000002", de_round_half_even_round_trips_sign_seed_000002),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000003", de_round_half_even_round_trips_sign_seed_000003),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000004", de_round_half_even_round_trips_sign_seed_000004),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000005", de_round_half_even_round_trips_sign_seed_000005),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000006", de_round_half_even_round_trips_sign_seed_000006),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000007", de_round_half_even_round_trips_sign_seed_000007),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000008", de_round_half_even_round_trips_sign_seed_000008),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000009", de_round_half_even_round_trips_sign_seed_000009),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000010", de_round_half_even_round_trips_sign_seed_000010),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000011", de_round_half_even_round_trips_sign_seed_000011),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000012", de_round_half_even_round_trips_sign_seed_000012),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000013", de_round_half_even_round_trips_sign_seed_000013),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000014", de_round_half_even_round_trips_sign_seed_000014),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000015", de_round_half_even_round_trips_sign_seed_000015),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000016", de_round_half_even_round_trips_sign_seed_000016),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000017", de_round_half_even_round_trips_sign_seed_000017),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000018", de_round_half_even_round_trips_sign_seed_000018),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000019", de_round_half_even_round_trips_sign_seed_000019),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000020", de_round_half_even_round_trips_sign_seed_000020),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000021", de_round_half_even_round_trips_sign_seed_000021),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000022", de_round_half_even_round_trips_sign_seed_000022),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000023", de_round_half_even_round_trips_sign_seed_000023),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000024", de_round_half_even_round_trips_sign_seed_000024),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000025", de_round_half_even_round_trips_sign_seed_000025),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000026", de_round_half_even_round_trips_sign_seed_000026),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000027", de_round_half_even_round_trips_sign_seed_000027),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000028", de_round_half_even_round_trips_sign_seed_000028),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000029", de_round_half_even_round_trips_sign_seed_000029),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000030", de_round_half_even_round_trips_sign_seed_000030),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000031", de_round_half_even_round_trips_sign_seed_000031),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000032", de_round_half_even_round_trips_sign_seed_000032),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000033", de_round_half_even_round_trips_sign_seed_000033),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000034", de_round_half_even_round_trips_sign_seed_000034),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000035", de_round_half_even_round_trips_sign_seed_000035),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000036", de_round_half_even_round_trips_sign_seed_000036),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000037", de_round_half_even_round_trips_sign_seed_000037),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000038", de_round_half_even_round_trips_sign_seed_000038),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000039", de_round_half_even_round_trips_sign_seed_000039),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000040", de_round_half_even_round_trips_sign_seed_000040),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000041", de_round_half_even_round_trips_sign_seed_000041),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000042", de_round_half_even_round_trips_sign_seed_000042),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000043", de_round_half_even_round_trips_sign_seed_000043),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000044", de_round_half_even_round_trips_sign_seed_000044),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000045", de_round_half_even_round_trips_sign_seed_000045),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000046", de_round_half_even_round_trips_sign_seed_000046),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000047", de_round_half_even_round_trips_sign_seed_000047),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000048", de_round_half_even_round_trips_sign_seed_000048),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000049", de_round_half_even_round_trips_sign_seed_000049),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000050", de_round_half_even_round_trips_sign_seed_000050),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000051", de_round_half_even_round_trips_sign_seed_000051),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000052", de_round_half_even_round_trips_sign_seed_000052),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000053", de_round_half_even_round_trips_sign_seed_000053),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000054", de_round_half_even_round_trips_sign_seed_000054),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000055", de_round_half_even_round_trips_sign_seed_000055),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000056", de_round_half_even_round_trips_sign_seed_000056),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000057", de_round_half_even_round_trips_sign_seed_000057),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000058", de_round_half_even_round_trips_sign_seed_000058),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000059", de_round_half_even_round_trips_sign_seed_000059),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000060", de_round_half_even_round_trips_sign_seed_000060),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000061", de_round_half_even_round_trips_sign_seed_000061),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000062", de_round_half_even_round_trips_sign_seed_000062),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000063", de_round_half_even_round_trips_sign_seed_000063),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000064", de_round_half_even_round_trips_sign_seed_000064),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000065", de_round_half_even_round_trips_sign_seed_000065),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000066", de_round_half_even_round_trips_sign_seed_000066),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000067", de_round_half_even_round_trips_sign_seed_000067),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000068", de_round_half_even_round_trips_sign_seed_000068),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000069", de_round_half_even_round_trips_sign_seed_000069),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000070", de_round_half_even_round_trips_sign_seed_000070),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000071", de_round_half_even_round_trips_sign_seed_000071),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000072", de_round_half_even_round_trips_sign_seed_000072),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000073", de_round_half_even_round_trips_sign_seed_000073),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000074", de_round_half_even_round_trips_sign_seed_000074),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000075", de_round_half_even_round_trips_sign_seed_000075),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000076", de_round_half_even_round_trips_sign_seed_000076),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000077", de_round_half_even_round_trips_sign_seed_000077),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000078", de_round_half_even_round_trips_sign_seed_000078),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000079", de_round_half_even_round_trips_sign_seed_000079),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000080", de_round_half_even_round_trips_sign_seed_000080),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000081", de_round_half_even_round_trips_sign_seed_000081),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000082", de_round_half_even_round_trips_sign_seed_000082),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000083", de_round_half_even_round_trips_sign_seed_000083),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000084", de_round_half_even_round_trips_sign_seed_000084),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000085", de_round_half_even_round_trips_sign_seed_000085),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000086", de_round_half_even_round_trips_sign_seed_000086),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000087", de_round_half_even_round_trips_sign_seed_000087),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000088", de_round_half_even_round_trips_sign_seed_000088),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000089", de_round_half_even_round_trips_sign_seed_000089),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000090", de_round_half_even_round_trips_sign_seed_000090),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000091", de_round_half_even_round_trips_sign_seed_000091),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000092", de_round_half_even_round_trips_sign_seed_000092),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000093", de_round_half_even_round_trips_sign_seed_000093),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000094", de_round_half_even_round_trips_sign_seed_000094),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000095", de_round_half_even_round_trips_sign_seed_000095),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000096", de_round_half_even_round_trips_sign_seed_000096),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000097", de_round_half_even_round_trips_sign_seed_000097),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000098", de_round_half_even_round_trips_sign_seed_000098),
        ("dsn_exporter::property_campaigns::de_round_half_even_round_trips_sign_seed_000099", de_round_half_even_round_trips_sign_seed_000099),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000000", de_round_half_even_idempotent_seed_000000),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000001", de_round_half_even_idempotent_seed_000001),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000002", de_round_half_even_idempotent_seed_000002),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000003", de_round_half_even_idempotent_seed_000003),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000004", de_round_half_even_idempotent_seed_000004),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000005", de_round_half_even_idempotent_seed_000005),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000006", de_round_half_even_idempotent_seed_000006),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000007", de_round_half_even_idempotent_seed_000007),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000008", de_round_half_even_idempotent_seed_000008),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000009", de_round_half_even_idempotent_seed_000009),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000010", de_round_half_even_idempotent_seed_000010),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000011", de_round_half_even_idempotent_seed_000011),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000012", de_round_half_even_idempotent_seed_000012),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000013", de_round_half_even_idempotent_seed_000013),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000014", de_round_half_even_idempotent_seed_000014),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000015", de_round_half_even_idempotent_seed_000015),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000016", de_round_half_even_idempotent_seed_000016),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000017", de_round_half_even_idempotent_seed_000017),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000018", de_round_half_even_idempotent_seed_000018),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000019", de_round_half_even_idempotent_seed_000019),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000020", de_round_half_even_idempotent_seed_000020),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000021", de_round_half_even_idempotent_seed_000021),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000022", de_round_half_even_idempotent_seed_000022),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000023", de_round_half_even_idempotent_seed_000023),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000024", de_round_half_even_idempotent_seed_000024),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000025", de_round_half_even_idempotent_seed_000025),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000026", de_round_half_even_idempotent_seed_000026),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000027", de_round_half_even_idempotent_seed_000027),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000028", de_round_half_even_idempotent_seed_000028),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000029", de_round_half_even_idempotent_seed_000029),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000030", de_round_half_even_idempotent_seed_000030),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000031", de_round_half_even_idempotent_seed_000031),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000032", de_round_half_even_idempotent_seed_000032),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000033", de_round_half_even_idempotent_seed_000033),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000034", de_round_half_even_idempotent_seed_000034),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000035", de_round_half_even_idempotent_seed_000035),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000036", de_round_half_even_idempotent_seed_000036),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000037", de_round_half_even_idempotent_seed_000037),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000038", de_round_half_even_idempotent_seed_000038),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000039", de_round_half_even_idempotent_seed_000039),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000040", de_round_half_even_idempotent_seed_000040),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000041", de_round_half_even_idempotent_seed_000041),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000042", de_round_half_even_idempotent_seed_000042),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000043", de_round_half_even_idempotent_seed_000043),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000044", de_round_half_even_idempotent_seed_000044),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000045", de_round_half_even_idempotent_seed_000045),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000046", de_round_half_even_idempotent_seed_000046),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000047", de_round_half_even_idempotent_seed_000047),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000048", de_round_half_even_idempotent_seed_000048),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000049", de_round_half_even_idempotent_seed_000049),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000050", de_round_half_even_idempotent_seed_000050),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000051", de_round_half_even_idempotent_seed_000051),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000052", de_round_half_even_idempotent_seed_000052),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000053", de_round_half_even_idempotent_seed_000053),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000054", de_round_half_even_idempotent_seed_000054),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000055", de_round_half_even_idempotent_seed_000055),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000056", de_round_half_even_idempotent_seed_000056),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000057", de_round_half_even_idempotent_seed_000057),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000058", de_round_half_even_idempotent_seed_000058),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000059", de_round_half_even_idempotent_seed_000059),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000060", de_round_half_even_idempotent_seed_000060),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000061", de_round_half_even_idempotent_seed_000061),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000062", de_round_half_even_idempotent_seed_000062),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000063", de_round_half_even_idempotent_seed_000063),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000064", de_round_half_even_idempotent_seed_000064),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000065", de_round_half_even_idempotent_seed_000065),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000066", de_round_half_even_idempotent_seed_000066),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000067", de_round_half_even_idempotent_seed_000067),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000068", de_round_half_even_idempotent_seed_000068),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000069", de_round_half_even_idempotent_seed_000069),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000070", de_round_half_even_idempotent_seed_000070),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000071", de_round_half_even_idempotent_seed_000071),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000072", de_round_half_even_idempotent_seed_000072),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000073", de_round_half_even_idempotent_seed_000073),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000074", de_round_half_even_idempotent_seed_000074),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000075", de_round_half_even_idempotent_seed_000075),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000076", de_round_half_even_idempotent_seed_000076),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000077", de_round_half_even_idempotent_seed_000077),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000078", de_round_half_even_idempotent_seed_000078),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000079", de_round_half_even_idempotent_seed_000079),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000080", de_round_half_even_idempotent_seed_000080),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000081", de_round_half_even_idempotent_seed_000081),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000082", de_round_half_even_idempotent_seed_000082),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000083", de_round_half_even_idempotent_seed_000083),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000084", de_round_half_even_idempotent_seed_000084),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000085", de_round_half_even_idempotent_seed_000085),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000086", de_round_half_even_idempotent_seed_000086),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000087", de_round_half_even_idempotent_seed_000087),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000088", de_round_half_even_idempotent_seed_000088),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000089", de_round_half_even_idempotent_seed_000089),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000090", de_round_half_even_idempotent_seed_000090),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000091", de_round_half_even_idempotent_seed_000091),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000092", de_round_half_even_idempotent_seed_000092),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000093", de_round_half_even_idempotent_seed_000093),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000094", de_round_half_even_idempotent_seed_000094),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000095", de_round_half_even_idempotent_seed_000095),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000096", de_round_half_even_idempotent_seed_000096),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000097", de_round_half_even_idempotent_seed_000097),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000098", de_round_half_even_idempotent_seed_000098),
        ("dsn_exporter::property_campaigns::de_round_half_even_idempotent_seed_000099", de_round_half_even_idempotent_seed_000099),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000000", de_natural_sort_key_total_order_seed_000000),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000001", de_natural_sort_key_total_order_seed_000001),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000002", de_natural_sort_key_total_order_seed_000002),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000003", de_natural_sort_key_total_order_seed_000003),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000004", de_natural_sort_key_total_order_seed_000004),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000005", de_natural_sort_key_total_order_seed_000005),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000006", de_natural_sort_key_total_order_seed_000006),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000007", de_natural_sort_key_total_order_seed_000007),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000008", de_natural_sort_key_total_order_seed_000008),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000009", de_natural_sort_key_total_order_seed_000009),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000010", de_natural_sort_key_total_order_seed_000010),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000011", de_natural_sort_key_total_order_seed_000011),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000012", de_natural_sort_key_total_order_seed_000012),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000013", de_natural_sort_key_total_order_seed_000013),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000014", de_natural_sort_key_total_order_seed_000014),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000015", de_natural_sort_key_total_order_seed_000015),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000016", de_natural_sort_key_total_order_seed_000016),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000017", de_natural_sort_key_total_order_seed_000017),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000018", de_natural_sort_key_total_order_seed_000018),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000019", de_natural_sort_key_total_order_seed_000019),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000020", de_natural_sort_key_total_order_seed_000020),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000021", de_natural_sort_key_total_order_seed_000021),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000022", de_natural_sort_key_total_order_seed_000022),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000023", de_natural_sort_key_total_order_seed_000023),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000024", de_natural_sort_key_total_order_seed_000024),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000025", de_natural_sort_key_total_order_seed_000025),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000026", de_natural_sort_key_total_order_seed_000026),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000027", de_natural_sort_key_total_order_seed_000027),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000028", de_natural_sort_key_total_order_seed_000028),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000029", de_natural_sort_key_total_order_seed_000029),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000030", de_natural_sort_key_total_order_seed_000030),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000031", de_natural_sort_key_total_order_seed_000031),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000032", de_natural_sort_key_total_order_seed_000032),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000033", de_natural_sort_key_total_order_seed_000033),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000034", de_natural_sort_key_total_order_seed_000034),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000035", de_natural_sort_key_total_order_seed_000035),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000036", de_natural_sort_key_total_order_seed_000036),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000037", de_natural_sort_key_total_order_seed_000037),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000038", de_natural_sort_key_total_order_seed_000038),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000039", de_natural_sort_key_total_order_seed_000039),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000040", de_natural_sort_key_total_order_seed_000040),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000041", de_natural_sort_key_total_order_seed_000041),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000042", de_natural_sort_key_total_order_seed_000042),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000043", de_natural_sort_key_total_order_seed_000043),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000044", de_natural_sort_key_total_order_seed_000044),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000045", de_natural_sort_key_total_order_seed_000045),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000046", de_natural_sort_key_total_order_seed_000046),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000047", de_natural_sort_key_total_order_seed_000047),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000048", de_natural_sort_key_total_order_seed_000048),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000049", de_natural_sort_key_total_order_seed_000049),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000050", de_natural_sort_key_total_order_seed_000050),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000051", de_natural_sort_key_total_order_seed_000051),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000052", de_natural_sort_key_total_order_seed_000052),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000053", de_natural_sort_key_total_order_seed_000053),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000054", de_natural_sort_key_total_order_seed_000054),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000055", de_natural_sort_key_total_order_seed_000055),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000056", de_natural_sort_key_total_order_seed_000056),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000057", de_natural_sort_key_total_order_seed_000057),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000058", de_natural_sort_key_total_order_seed_000058),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000059", de_natural_sort_key_total_order_seed_000059),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000060", de_natural_sort_key_total_order_seed_000060),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000061", de_natural_sort_key_total_order_seed_000061),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000062", de_natural_sort_key_total_order_seed_000062),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000063", de_natural_sort_key_total_order_seed_000063),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000064", de_natural_sort_key_total_order_seed_000064),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000065", de_natural_sort_key_total_order_seed_000065),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000066", de_natural_sort_key_total_order_seed_000066),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000067", de_natural_sort_key_total_order_seed_000067),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000068", de_natural_sort_key_total_order_seed_000068),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000069", de_natural_sort_key_total_order_seed_000069),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000070", de_natural_sort_key_total_order_seed_000070),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000071", de_natural_sort_key_total_order_seed_000071),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000072", de_natural_sort_key_total_order_seed_000072),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000073", de_natural_sort_key_total_order_seed_000073),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000074", de_natural_sort_key_total_order_seed_000074),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000075", de_natural_sort_key_total_order_seed_000075),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000076", de_natural_sort_key_total_order_seed_000076),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000077", de_natural_sort_key_total_order_seed_000077),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000078", de_natural_sort_key_total_order_seed_000078),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000079", de_natural_sort_key_total_order_seed_000079),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000080", de_natural_sort_key_total_order_seed_000080),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000081", de_natural_sort_key_total_order_seed_000081),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000082", de_natural_sort_key_total_order_seed_000082),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000083", de_natural_sort_key_total_order_seed_000083),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000084", de_natural_sort_key_total_order_seed_000084),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000085", de_natural_sort_key_total_order_seed_000085),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000086", de_natural_sort_key_total_order_seed_000086),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000087", de_natural_sort_key_total_order_seed_000087),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000088", de_natural_sort_key_total_order_seed_000088),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000089", de_natural_sort_key_total_order_seed_000089),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000090", de_natural_sort_key_total_order_seed_000090),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000091", de_natural_sort_key_total_order_seed_000091),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000092", de_natural_sort_key_total_order_seed_000092),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000093", de_natural_sort_key_total_order_seed_000093),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000094", de_natural_sort_key_total_order_seed_000094),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000095", de_natural_sort_key_total_order_seed_000095),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000096", de_natural_sort_key_total_order_seed_000096),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000097", de_natural_sort_key_total_order_seed_000097),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000098", de_natural_sort_key_total_order_seed_000098),
        ("dsn_exporter::property_campaigns::de_natural_sort_key_total_order_seed_000099", de_natural_sort_key_total_order_seed_000099),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000000", de_format_fixed_round_trips_precision_seed_000000),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000001", de_format_fixed_round_trips_precision_seed_000001),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000002", de_format_fixed_round_trips_precision_seed_000002),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000003", de_format_fixed_round_trips_precision_seed_000003),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000004", de_format_fixed_round_trips_precision_seed_000004),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000005", de_format_fixed_round_trips_precision_seed_000005),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000006", de_format_fixed_round_trips_precision_seed_000006),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000007", de_format_fixed_round_trips_precision_seed_000007),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000008", de_format_fixed_round_trips_precision_seed_000008),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000009", de_format_fixed_round_trips_precision_seed_000009),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000010", de_format_fixed_round_trips_precision_seed_000010),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000011", de_format_fixed_round_trips_precision_seed_000011),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000012", de_format_fixed_round_trips_precision_seed_000012),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000013", de_format_fixed_round_trips_precision_seed_000013),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000014", de_format_fixed_round_trips_precision_seed_000014),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000015", de_format_fixed_round_trips_precision_seed_000015),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000016", de_format_fixed_round_trips_precision_seed_000016),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000017", de_format_fixed_round_trips_precision_seed_000017),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000018", de_format_fixed_round_trips_precision_seed_000018),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000019", de_format_fixed_round_trips_precision_seed_000019),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000020", de_format_fixed_round_trips_precision_seed_000020),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000021", de_format_fixed_round_trips_precision_seed_000021),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000022", de_format_fixed_round_trips_precision_seed_000022),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000023", de_format_fixed_round_trips_precision_seed_000023),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000024", de_format_fixed_round_trips_precision_seed_000024),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000025", de_format_fixed_round_trips_precision_seed_000025),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000026", de_format_fixed_round_trips_precision_seed_000026),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000027", de_format_fixed_round_trips_precision_seed_000027),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000028", de_format_fixed_round_trips_precision_seed_000028),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000029", de_format_fixed_round_trips_precision_seed_000029),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000030", de_format_fixed_round_trips_precision_seed_000030),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000031", de_format_fixed_round_trips_precision_seed_000031),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000032", de_format_fixed_round_trips_precision_seed_000032),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000033", de_format_fixed_round_trips_precision_seed_000033),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000034", de_format_fixed_round_trips_precision_seed_000034),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000035", de_format_fixed_round_trips_precision_seed_000035),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000036", de_format_fixed_round_trips_precision_seed_000036),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000037", de_format_fixed_round_trips_precision_seed_000037),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000038", de_format_fixed_round_trips_precision_seed_000038),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000039", de_format_fixed_round_trips_precision_seed_000039),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000040", de_format_fixed_round_trips_precision_seed_000040),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000041", de_format_fixed_round_trips_precision_seed_000041),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000042", de_format_fixed_round_trips_precision_seed_000042),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000043", de_format_fixed_round_trips_precision_seed_000043),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000044", de_format_fixed_round_trips_precision_seed_000044),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000045", de_format_fixed_round_trips_precision_seed_000045),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000046", de_format_fixed_round_trips_precision_seed_000046),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000047", de_format_fixed_round_trips_precision_seed_000047),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000048", de_format_fixed_round_trips_precision_seed_000048),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000049", de_format_fixed_round_trips_precision_seed_000049),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000050", de_format_fixed_round_trips_precision_seed_000050),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000051", de_format_fixed_round_trips_precision_seed_000051),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000052", de_format_fixed_round_trips_precision_seed_000052),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000053", de_format_fixed_round_trips_precision_seed_000053),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000054", de_format_fixed_round_trips_precision_seed_000054),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000055", de_format_fixed_round_trips_precision_seed_000055),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000056", de_format_fixed_round_trips_precision_seed_000056),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000057", de_format_fixed_round_trips_precision_seed_000057),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000058", de_format_fixed_round_trips_precision_seed_000058),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000059", de_format_fixed_round_trips_precision_seed_000059),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000060", de_format_fixed_round_trips_precision_seed_000060),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000061", de_format_fixed_round_trips_precision_seed_000061),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000062", de_format_fixed_round_trips_precision_seed_000062),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000063", de_format_fixed_round_trips_precision_seed_000063),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000064", de_format_fixed_round_trips_precision_seed_000064),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000065", de_format_fixed_round_trips_precision_seed_000065),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000066", de_format_fixed_round_trips_precision_seed_000066),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000067", de_format_fixed_round_trips_precision_seed_000067),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000068", de_format_fixed_round_trips_precision_seed_000068),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000069", de_format_fixed_round_trips_precision_seed_000069),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000070", de_format_fixed_round_trips_precision_seed_000070),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000071", de_format_fixed_round_trips_precision_seed_000071),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000072", de_format_fixed_round_trips_precision_seed_000072),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000073", de_format_fixed_round_trips_precision_seed_000073),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000074", de_format_fixed_round_trips_precision_seed_000074),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000075", de_format_fixed_round_trips_precision_seed_000075),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000076", de_format_fixed_round_trips_precision_seed_000076),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000077", de_format_fixed_round_trips_precision_seed_000077),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000078", de_format_fixed_round_trips_precision_seed_000078),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000079", de_format_fixed_round_trips_precision_seed_000079),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000080", de_format_fixed_round_trips_precision_seed_000080),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000081", de_format_fixed_round_trips_precision_seed_000081),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000082", de_format_fixed_round_trips_precision_seed_000082),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000083", de_format_fixed_round_trips_precision_seed_000083),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000084", de_format_fixed_round_trips_precision_seed_000084),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000085", de_format_fixed_round_trips_precision_seed_000085),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000086", de_format_fixed_round_trips_precision_seed_000086),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000087", de_format_fixed_round_trips_precision_seed_000087),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000088", de_format_fixed_round_trips_precision_seed_000088),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000089", de_format_fixed_round_trips_precision_seed_000089),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000090", de_format_fixed_round_trips_precision_seed_000090),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000091", de_format_fixed_round_trips_precision_seed_000091),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000092", de_format_fixed_round_trips_precision_seed_000092),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000093", de_format_fixed_round_trips_precision_seed_000093),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000094", de_format_fixed_round_trips_precision_seed_000094),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000095", de_format_fixed_round_trips_precision_seed_000095),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000096", de_format_fixed_round_trips_precision_seed_000096),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000097", de_format_fixed_round_trips_precision_seed_000097),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000098", de_format_fixed_round_trips_precision_seed_000098),
        ("dsn_exporter::property_campaigns::de_format_fixed_round_trips_precision_seed_000099", de_format_fixed_round_trips_precision_seed_000099),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: property_campaigns ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
// A sibling module rather than `#[test] fn`s mixed into `tests` above, matching
// `pyfmt.rs`, `stackup_validator.rs`, `placer_core/units.rs` and
// `placer_core/placer_compute.rs`.  `proptest` is a dev-dependency, so it is
// absent from the ordinary (non-test) build the `wasm32` registry compiles
// into; keeping these apart is what lets the deterministic tests above join
// the tier instead of being excluded alongside them.
#[cfg(all(test, feature = "python"))]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::*;

    // -- py_round_half_even proptest -------------------------------------

    #[test]
    fn py_round_half_even_round_trips_sign() {
        use proptest::prelude::*;
        proptest!(|(x in -1e6f64..1e6f64)| {
            let r = py_round_half_even(x);
            // Reversibility: the int representation is within 0.5 of x
            let diff = (r as f64 - x).abs();
            prop_assert!(diff <= 0.5 + 1e-12);
        });
    }

    #[test]
    fn py_round_half_even_idempotent() {
        use proptest::prelude::*;
        proptest!(|(x in -1e6f64..1e6f64)| {
            let r = py_round_half_even(x);
            prop_assert_eq!(py_round_half_even(r as f64), r);
        });
    }

    // -- natural_sort_key proptest ---------------------------------------

    #[test]
    fn natural_sort_key_total_order() {
        use proptest::prelude::*;
        let pat = "[a-zA-Z0-9]{0,20}";
        proptest!(|(a in pat, b in pat, c in pat)| {
            let ka = natural_sort_key(&a);
            let kb = natural_sort_key(&b);
            let kc = natural_sort_key(&c);
            // Transitivity: if a <= b and b <= c then a <= c
            if ka <= kb && kb <= kc {
                prop_assert!(ka <= kc);
            }
        });
    }

    // -- py_format_fixed proptest ----------------------------------------

    #[test]
    fn py_format_fixed_round_trips_precision() {
        use proptest::prelude::*;
        proptest!(|(x in -1e6f64..1e6f64, prec in 0usize..6usize)| {
            let s = py_format_fixed(x, prec);
            // The output should have exactly `prec` digits after the decimal
            // (unless it's the inf/nan path, but those don't occur in normal range).
            if x.is_finite() && prec > 0 {
                prop_assert!(s.contains('.'),
                    "precision {} on {:?} produced no decimal: '{}'", prec, x, s);
                let after_dot = s.split('.').nth(1).unwrap();
                prop_assert_eq!(after_dot.len(), prec,
                    "precision {} on {:?} gave '{}' with {} digits after dot",
                    prec, x, s, after_dot.len());
            }
        });
    }
}
