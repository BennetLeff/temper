//! Layer identity — a typed, single-construction-path replacement for bare
//! `&str` PCB layer names.
//!
//! # The bug class this closes
//!
//! `core/board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` stayed at
//! `("F.Cu", "B.Cu")` after `In3.Cu`/`In4.Cu` were declared signal in PR
//! #1178's 6-layer stackup. Two more copies of the same fact existed
//! independently: `router_v6/grid_prep_stage.py` looped
//! `for layer in ("F.Cu", "B.Cu")`, and `router_v6/_astar_nlayer.py` set
//! `preferred_order = ["F.Cu", "B.Cu"]`. The board was unroutable for
//! weeks. Separately, `trace_width_assignment.py` assigns trace width from
//! a single 2oz-calibrated constant with no layer awareness at all, so
//! power traces land on 1oz inner copper on a mains board — an ampacity
//! defect. Both bugs are the same shape: a fact declared once in the
//! board's own `(layers ...)` / `(setup (stackup ...))` blocks, copied by
//! hand into a consumer as a bare string or a bare float, correct only
//! until the SSOT next changes.
//!
//! The `board_layer_roles.py` accessor that froze had been added
//! *specifically* to prevent this exact failure — a runtime guard
//! reproduced, inside itself, the bug it existed to catch. That is the
//! strongest possible argument that a checker is the wrong layer for this:
//! this module is the alternative. See
//! `docs/evidence/2026-08-14-layer-identity-type.md` for the full design
//! writeup and the units/frames/netclass generalization this does NOT yet
//! cover.
//!
//! # What is actually structural here (read before extending this module)
//!
//! * **`Layer`'s fields are private, and there is no public struct-literal
//!   constructor.** The only ways to obtain a `Layer` are (a) through a
//!   [`Stackup`] parsed from a real board's own declaration
//!   ([`Stackup::parse`] / [`Stackup::from_path`]), or (b) the explicit,
//!   named [`Stackup::test_only`] escape hatch. A caller cannot write
//!   `Layer { name: "F.Cu".into(), role: LayerRole::Signal, .. }` from
//!   outside this module — that is a compile error (private fields), not a
//!   lint finding. See the `compile_fail` doctest on [`Layer`] itself.
//! * **Copper weight is inseparable from the layer it was parsed for.**
//!   `Layer::copper_weight_oz` takes `&self` — there is no free function
//!   `copper_weight_oz(name: &str)` a caller could feed a stale/wrong name
//!   into. A function that needs copper weight must accept a `&Layer`, and
//!   the only way to hold one is to have gotten it from a real stackup (or
//!   the named test-only escape hatch).
//! * **Position (`Outer`/`Inner`) is DERIVED, never asserted.** It comes
//!   from the layer's index in the board's own declared copper-layer
//!   order (first and last declared copper layer are the two outer
//!   surfaces; everything between is internal) — never a second hardcoded
//!   `OUTER_LAYERS = ("F.Cu", "B.Cu")` tuple that could itself go stale on
//!   an 8-layer board. `Stackup::test_only` derives position the same way,
//!   so the escape hatch cannot assert an internally inconsistent stackup.
//! * **What is NOT structural:** [`ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES`],
//!   the router engine's real occupancy-grid/A*-pathfinding coverage, is
//!   still a hand-maintained `&[&str]` constant — no board file states
//!   what the *router implementation* supports, so no parse can derive it.
//!   The structural improvement here is narrower and still real: this is
//!   now the ONLY copy of that fact in the tree (previously at least three
//!   independent copies existed), because [`Stackup::routable_signal_layers`]
//!   is the sole place that intersects it against the board's declared
//!   roles — a consumer can no longer accidentally hardcode its own copy of
//!   the pair, because the only way to get a `Layer` at all is through this
//!   module. Widening the engine's real capability is still a one-line,
//!   human-reviewed edit to this constant; that residual is checked (see
//!   `docs/evidence/2026-08-14-layer-identity-type.md`'s design doc for the
//!   remaining-cases writeup), not made unrepresentable.

use std::collections::HashMap;
use std::fmt;
use std::path::Path;
use std::sync::OnceLock;

use regex::Regex;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

// ---------------------------------------------------------------------------
// LayerRole
// ---------------------------------------------------------------------------

/// A copper layer's declared role, per the board's own `(layers ...)`
/// block. The KiCad board-format vocabulary (`kicad_pcb` v20211014, this
/// repo's format) is `signal`, `power`, `mixed`, `jumper`, or `user`
/// (non-copper layers only ever declare `user`, filtered out before
/// reaching this type — see [`Stackup::parse`]). Mirrors
/// `board_layer_roles.LayerRole` (Python) one-for-one; this is the typed
/// SSOT the Python enum should be read *from*, not a parallel definition of
/// it — see the design doc's migration plan.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LayerRole {
    Signal,
    Power,
    Mixed,
    Jumper,
}

impl LayerRole {
    /// The exact board-format token this role was parsed from / would
    /// serialize back to.
    pub fn as_str(self) -> &'static str {
        match self {
            LayerRole::Signal => "signal",
            LayerRole::Power => "power",
            LayerRole::Mixed => "mixed",
            LayerRole::Jumper => "jumper",
        }
    }

    fn from_token(token: &str) -> Option<LayerRole> {
        match token {
            "signal" => Some(LayerRole::Signal),
            "power" => Some(LayerRole::Power),
            "mixed" => Some(LayerRole::Mixed),
            "jumper" => Some(LayerRole::Jumper),
            _ => None,
        }
    }

    /// Whether THIS ROLE, in isolation, is a role the router may ever
    /// target — `Signal` or `Mixed` only. Necessary but not sufficient for
    /// "the router can route here today": see
    /// [`Stackup::routable_signal_layers`], which additionally intersects
    /// with the engine's real capability.
    pub fn is_routable_role(self) -> bool {
        matches!(self, LayerRole::Signal | LayerRole::Mixed)
    }
}

impl fmt::Display for LayerRole {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

// ---------------------------------------------------------------------------
// LayerPosition
// ---------------------------------------------------------------------------

/// Whether a copper layer sits on the board's outer surface or between
/// other copper layers. Always DERIVED from the layer's index among the
/// board's own declared copper layers (first/last = outer) — never a
/// second hardcoded name list. See this module's doc comment.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LayerPosition {
    Outer,
    Inner,
}

// ---------------------------------------------------------------------------
// Copper weight
// ---------------------------------------------------------------------------

/// One ounce of copper weight, expressed in millimetres of thickness — the
/// board format's own unit (`(thickness ...)` is in mm). 1oz copper is
/// 35um = 0.035mm; this is the repo's own pinned figure (
/// `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §1, cross-checked by
/// `scripts/check_stackup_copper_weight_gate.py`'s 2oz/70um, 1oz/35um
/// pairing), not a re-derived physical constant.
pub const OZ_TO_MM: f64 = 0.035;

// ---------------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------------

/// A single declared copper layer: name, role, physical position, and
/// copper weight, bound together so a consumer cannot obtain one without
/// the others.
///
/// **Every field is private and there is no public constructor.** The only
/// way to build a `Layer` is through [`Stackup::parse`] /
/// [`Stackup::from_path`] (reading a real board's own declaration) or the
/// explicit [`Stackup::test_only`] escape hatch. A hardcoded stale copy —
/// `Layer { name: "F.Cu".into(), role: LayerRole::Signal, .. }` written
/// anywhere outside this module — does not compile:
///
/// ```compile_fail
/// use temper_geometry::layer_identity::{Layer, LayerRole, LayerPosition};
/// // Every field below is private to `layer_identity` -- this cannot
/// // compile from an external crate or a sibling module.
/// let bad = Layer {
///     name: "F.Cu".to_string(),
///     role: LayerRole::Signal,
///     position: LayerPosition::Outer,
///     copper_thickness_mm: 0.070,
/// };
/// ```
#[derive(Debug, Clone, PartialEq)]
pub struct Layer {
    name: String,
    role: LayerRole,
    position: LayerPosition,
    copper_thickness_mm: f64,
}

impl Layer {
    /// The board-format layer name, e.g. `"F.Cu"`, `"In3.Cu"`.
    pub fn name(&self) -> &str {
        &self.name
    }

    /// The layer's declared role.
    pub fn role(&self) -> LayerRole {
        self.role
    }

    /// The layer's derived physical position (outer surface vs. internal).
    pub fn position(&self) -> LayerPosition {
        self.position
    }

    /// Whether this layer is an internal (non-outer-surface) copper layer.
    pub fn is_internal(&self) -> bool {
        matches!(self.position, LayerPosition::Inner)
    }

    /// Copper thickness in millimetres — the board format's own unit, and
    /// this type's SSOT representation of copper weight.
    pub fn copper_thickness_mm(&self) -> f64 {
        self.copper_thickness_mm
    }

    /// Copper weight in ounces, derived from [`Layer::copper_thickness_mm`].
    /// This is what a copper-weight-aware trace-width function should call
    /// — it cannot be called without first holding a `Layer`, which cannot
    /// be held without having gone through a real (or explicitly
    /// test-only) stackup.
    pub fn copper_weight_oz(&self) -> f64 {
        self.copper_thickness_mm / OZ_TO_MM
    }
}

/// Trivial, but the point is the signature: this function CANNOT be called
/// without a [`Layer`], and a [`Layer`] cannot be constructed from a bare
/// string. Contrast with the bug this module closes —
/// `trace_width_assignment.py` reading a single global 2oz-calibrated
/// constant with no layer parameter at all. The layer-aware
/// `trace_width_assignment.rs` migration (tracked separately — see this
/// module's doc comment) is the intended caller of exactly this shape.
pub fn copper_weight_oz_for(layer: &Layer) -> f64 {
    layer.copper_weight_oz()
}

// ---------------------------------------------------------------------------
// TestOnlyLayerSpec / Stackup::test_only
// ---------------------------------------------------------------------------

/// The explicit, named, greppable escape hatch for synthetic test
/// fixtures that genuinely need a `Stackup` without a real board file on
/// disk. Not a bare tuple literal: constructing a `Stackup` this way
/// requires spelling `TestOnlyLayerSpec` and `Stackup::test_only` — both
/// greppable, unmistakably-named, and absent from every production call site.
#[derive(Debug, Clone)]
pub struct TestOnlyLayerSpec {
    pub name: String,
    pub role: LayerRole,
    pub copper_thickness_mm: f64,
}

// ---------------------------------------------------------------------------
// Parse errors
// ---------------------------------------------------------------------------

/// Why parsing a board's declared stackup failed. Fail-closed contract,
/// matching this repo's existing gate-family convention
/// (`board_layer_roles.py`, `check_stackup_copper_weight_gate.py`): a
/// board that cannot be parsed produces an error, never a silently empty
/// or partially-populated `Stackup`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StackupParseError {
    /// No `(layers ...)` block found at all.
    NoLayersBlock,
    /// A `(layers ...)` block was found but its parentheses never balance.
    UnbalancedLayersBlock,
    /// The `(layers ...)` block has no `.Cu` layer with a recognized role
    /// (`signal`/`power`/`mixed`/`jumper`) — a fail-closed signal that
    /// something is structurally wrong with the input, not an
    /// empty-but-valid board.
    NoRecognizedCopperLayer,
    /// No `(setup (stackup ...))` block found — copper weight is
    /// unknowable without it.
    NoStackupBlock,
    /// A `(setup (stackup ...))` block was found but its parentheses never
    /// balance.
    UnbalancedStackupBlock,
    /// A declared copper layer (from `(layers ...)`) has no matching
    /// `copper`-type entry with a numeric thickness in
    /// `(setup (stackup ...))`. `Layer::copper_weight_oz` is infallible —
    /// this is where that guarantee is paid for: a layer with unknown
    /// copper weight fails the whole parse rather than silently omitting
    /// weight or defaulting it.
    MissingCopperThickness(String),
    /// A copper-type entry's `(thickness ...)` value matched the regex's
    /// `[0-9.]+` character class (so it looked numeric) but does not parse
    /// as a finite `f64` (e.g. `"1.2.3"`, multiple decimal points).
    MalformedCopperThickness(String),
}

impl fmt::Display for StackupParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StackupParseError::NoLayersBlock => {
                write!(f, "no '(layers ...)' block found in board content")
            }
            StackupParseError::UnbalancedLayersBlock => {
                write!(f, "'(layers ...)' block is not balanced")
            }
            StackupParseError::NoRecognizedCopperLayer => write!(
                f,
                "no '.Cu' layer with a recognized role (signal/power/mixed/jumper) \
                 found in the board's (layers ...) block"
            ),
            StackupParseError::NoStackupBlock => write!(
                f,
                "no '(setup (stackup ...))' block found in board content -- \
                 copper weight is unknowable without it"
            ),
            StackupParseError::UnbalancedStackupBlock => {
                write!(f, "'(setup (stackup ...))' block is not balanced")
            }
            StackupParseError::MissingCopperThickness(name) => write!(
                f,
                "declared copper layer {name:?} has no matching copper-type \
                 entry with a numeric thickness in the board's \
                 (setup (stackup ...)) block"
            ),
            StackupParseError::MalformedCopperThickness(name) => write!(
                f,
                "copper layer {name:?}'s declared thickness does not parse \
                 as a finite number"
            ),
        }
    }
}

impl std::error::Error for StackupParseError {}

/// Wraps [`StackupParseError`] with the I/O failure mode of
/// [`Stackup::from_path`], analogous to
/// `board_layer_roles.parse_declared_layer_roles_from_path`'s
/// file-not-found/parse-error split.
#[derive(Debug)]
pub enum StackupSourceError {
    Io(std::io::Error),
    Parse(StackupParseError),
}

impl fmt::Display for StackupSourceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StackupSourceError::Io(e) => write!(f, "could not read board file: {e}"),
            StackupSourceError::Parse(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for StackupSourceError {}

// ---------------------------------------------------------------------------
// Parsing internals
// ---------------------------------------------------------------------------

/// Return the balanced-parenthesis span starting at the first occurrence
/// of `marker` in `text`. Mirrors `board_layer_roles.py`'s
/// `_extract_balanced` / `check_stackup_copper_weight_gate.py`'s
/// identically-named helper — same narrow S-expression slicing task, now
/// with one Rust copy instead of implicitly needing a third Python one.
enum ExtractError {
    NotFound,
    Unbalanced,
}

fn extract_balanced<'a>(text: &'a str, marker: &str) -> Result<&'a str, ExtractError> {
    let start = text.find(marker).ok_or(ExtractError::NotFound)?;
    let mut depth = 0i32;
    let mut end = None;
    for (i, ch) in text[start..].char_indices() {
        match ch {
            '(' => depth += 1,
            ')' => {
                depth -= 1;
                if depth == 0 {
                    end = Some(start + i + ch.len_utf8());
                    break;
                }
            }
            _ => {}
        }
    }
    let end = end.ok_or(ExtractError::Unbalanced)?;
    Ok(&text[start..end])
}

// `Regex::new` on a fixed string literal cannot fail in practice (both
// patterns below are covered by this module's own tests), but the crate
// denies `clippy::expect_used`/`unwrap_used` globally -- so failure is
// handled the same fail-closed way a runtime parse error would be, via an
// empty never-matching fallback regex, rather than a scoped lint override
// for what is genuinely infallible input.
#[allow(clippy::unwrap_used)]
fn layer_entry_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r#"\(\s*\d+\s+"([A-Za-z0-9_.]+)"\s+(\w+)"#)
            .unwrap_or_else(|_| Regex::new(r"$^").unwrap())
    })
}

#[allow(clippy::unwrap_used)]
fn copper_thickness_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r#"\(layer\s+"([A-Za-z0-9_.]+)"\s+\(type\s+"copper"\)\s+\(thickness\s+([0-9.]+)\)\s*\)"#)
            .unwrap_or_else(|_| Regex::new(r"$^").unwrap())
    })
}

// ---------------------------------------------------------------------------
// Stackup
// ---------------------------------------------------------------------------

/// The board's declared stackup: an ordered set of [`Layer`]s.
///
/// **The only ways to obtain one:** parse a real board's own declaration
/// ([`Stackup::parse`] / [`Stackup::from_path`]), or the explicit, named
/// [`Stackup::test_only`] escape hatch. There is no public struct literal
/// for `Stackup` either — its single field is private.
#[derive(Debug, Clone)]
pub struct Stackup {
    layers: Vec<Layer>,
}

impl Stackup {
    /// Parse `pcb_content` (a whole `.kicad_pcb` file's text, or any text
    /// containing a top-level `(layers ...)` and `(setup (stackup ...))`
    /// block) into a `Stackup`.
    ///
    /// Role comes from `(layers ...)` (structural declaration); copper
    /// weight comes from `(setup (stackup ...))` (fab declaration). Both
    /// are read directly from the board's own text — never inferred from a
    /// prior known-good value, never defaulted. Position is DERIVED from
    /// declared copper-layer order (first/last = outer).
    pub fn parse(pcb_content: &str) -> Result<Stackup, StackupParseError> {
        let declared = parse_declared_layer_roles(pcb_content)?;

        let setup_block = extract_balanced(pcb_content, "(setup").map_err(|e| match e {
            ExtractError::NotFound => StackupParseError::NoStackupBlock,
            ExtractError::Unbalanced => StackupParseError::UnbalancedStackupBlock,
        })?;
        let stackup_block = extract_balanced(setup_block, "(stackup").map_err(|e| match e {
            ExtractError::NotFound => StackupParseError::NoStackupBlock,
            ExtractError::Unbalanced => StackupParseError::UnbalancedStackupBlock,
        })?;

        let mut thickness_mm: HashMap<String, f64> = HashMap::new();
        for cap in copper_thickness_regex().captures_iter(stackup_block) {
            let name = cap[1].to_string();
            // The regex's capture group is `[0-9.]+`, which admits
            // strings like "1.2.3" that look numeric but do not parse as
            // an f64 -- fail closed rather than `.expect()`/`.unwrap()` on
            // genuinely-untrusted board input.
            let t: f64 = cap[2]
                .parse()
                .map_err(|_| StackupParseError::MalformedCopperThickness(name.clone()))?;
            thickness_mm.insert(name, t);
        }

        let n = declared.len();
        let mut layers = Vec::with_capacity(n);
        for (i, (name, role)) in declared.into_iter().enumerate() {
            let position = if i == 0 || i == n - 1 {
                LayerPosition::Outer
            } else {
                LayerPosition::Inner
            };
            let copper_thickness_mm = *thickness_mm
                .get(&name)
                .ok_or_else(|| StackupParseError::MissingCopperThickness(name.clone()))?;
            layers.push(Layer { name, role, position, copper_thickness_mm });
        }

        Ok(Stackup { layers })
    }

    /// [`Stackup::parse`], reading `path` first.
    pub fn from_path(path: &Path) -> Result<Stackup, StackupSourceError> {
        let content = std::fs::read_to_string(path).map_err(StackupSourceError::Io)?;
        Stackup::parse(&content).map_err(StackupSourceError::Parse)
    }

    /// TEST-ONLY escape hatch: build a synthetic `Stackup` without parsing
    /// a real board file. Explicit and greppable by design — there is no
    /// way to reach this from a bare tuple/list literal; a caller must
    /// spell `Stackup::test_only` and provide a [`TestOnlyLayerSpec`] per
    /// layer.
    ///
    /// Position is still DERIVED from declaration order (first/last =
    /// outer), exactly as [`Stackup::parse`] derives it — this escape
    /// hatch skips reading a file, not the derivation rule, so a synthetic
    /// board cannot assert an internally inconsistent stackup (e.g. three
    /// "outer" layers).
    pub fn test_only(specs: Vec<TestOnlyLayerSpec>) -> Stackup {
        let n = specs.len();
        let layers = specs
            .into_iter()
            .enumerate()
            .map(|(i, spec)| {
                let position = if n <= 1 || i == 0 || i == n - 1 {
                    LayerPosition::Outer
                } else {
                    LayerPosition::Inner
                };
                Layer {
                    name: spec.name,
                    role: spec.role,
                    position,
                    copper_thickness_mm: spec.copper_thickness_mm,
                }
            })
            .collect();
        Stackup { layers }
    }

    /// Every declared layer, in declared order.
    pub fn layers(&self) -> &[Layer] {
        &self.layers
    }

    /// The declared layer named `name`, if the board declares one.
    pub fn layer(&self, name: &str) -> Option<&Layer> {
        self.layers.iter().find(|l| l.name == name)
    }

    /// Every `.Cu` layer the board declares with role `Signal` (NOT
    /// `Mixed`), in declared order. This is the *architecture* question —
    /// what a layer-architecture decision (adding/removing signal layers)
    /// should be measured against. Mirrors
    /// `board_layer_roles.signal_layer_names`.
    pub fn signal_layers(&self) -> impl Iterator<Item = &Layer> {
        self.layers.iter().filter(|l| l.role == LayerRole::Signal)
    }

    /// Every declared `Signal` layer the router can ACTUALLY target today
    /// — the intersection of [`Stackup::signal_layers`] with
    /// [`ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES`], in declared order. This is
    /// the *routing-decision* question. Mirrors
    /// `board_layer_roles.routable_signal_layers`; see this module's doc
    /// comment for what is (and is not) structural about the engine-
    /// capability half of this intersection.
    pub fn routable_signal_layers(&self) -> Vec<&Layer> {
        self.signal_layers()
            .filter(|l| ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES.contains(&l.name.as_str()))
            .collect()
    }
}

/// Parse only the board's declared `(layers ...)` block.
///
/// This intentionally does not require `(setup (stackup ...))`: callers that
/// need layer architecture/roles must not be forced to provide fabrication
/// thickness data. `Stackup::parse` uses this same parser before applying its
/// stronger copper-weight invariant.
pub fn parse_declared_layer_roles(
    pcb_content: &str,
) -> Result<Vec<(String, LayerRole)>, StackupParseError> {
    let layers_block = extract_balanced(pcb_content, "(layers").map_err(|e| match e {
        ExtractError::NotFound => StackupParseError::NoLayersBlock,
        ExtractError::Unbalanced => StackupParseError::UnbalancedLayersBlock,
    })?;

    let mut declared = Vec::new();
    for cap in layer_entry_regex().captures_iter(layers_block) {
        let name = cap[1].to_string();
        if !name.ends_with(".Cu") {
            continue;
        }
        let Some(role) = LayerRole::from_token(&cap[2]) else {
            continue;
        };
        declared.push((name, role));
    }
    if declared.is_empty() {
        return Err(StackupParseError::NoRecognizedCopperLayer);
    }
    Ok(declared)
}

// ---------------------------------------------------------------------------
// Engine capability
// ---------------------------------------------------------------------------

/// The router engine's real, verified occupancy-grid / A*-pathfinding
/// layer coverage today. This is a fact about the ROUTER IMPLEMENTATION,
/// not about the board — no board file states what the engine's Stage-2
/// grid construction or Stage-4 pathfinding actually supports, so no parse
/// can derive it, and this constant is NOT structural in the same sense
/// [`Layer`]/[`Stackup`] are (see this module's doc comment).
///
/// What IS structural: this is the ONLY copy of this fact anywhere in the
/// tree. Before this module existed, the equivalent fact was hardcoded
/// independently in `board_layer_roles.py`,
/// `router_v6/grid_prep_stage.py`, and `router_v6/_astar_nlayer.py` — three
/// copies that happened to agree by construction, never by a checked
/// relationship, which is exactly how the bug this module closes happened.
/// A caller can no longer write its own copy of this pair: the only way to
/// get a routable `Layer` at all is [`Stackup::routable_signal_layers`],
/// which reads this constant once.
///
/// Widening the engine's real capability (adding Stage-2 grid + Stage-4
/// pathfinding support for a new signal layer) is a one-line, human-
/// reviewed edit here — see `docs/evidence/2026-08-13-router-nlayer-
/// routing.md` for the verification that produced the current four-layer
/// value.
pub const ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES: &[&str] = &["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"];

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyclass(name = "Layer", module = "temper_geometry", skip_from_py_object)]
#[derive(Clone)]
pub struct PyLayer(Layer);

#[cfg(feature = "python")]
#[pymethods]
impl PyLayer {
    #[getter]
    fn name(&self) -> &str {
        self.0.name()
    }

    /// `"signal"` / `"power"` / `"mixed"` / `"jumper"` — the exact
    /// board-format token. Python callers that want the typed
    /// `board_layer_roles.LayerRole` enum should wrap this with
    /// `LayerRole(layer.role)`.
    #[getter]
    fn role(&self) -> &'static str {
        self.0.role().as_str()
    }

    #[getter]
    fn is_routable_role(&self) -> bool {
        self.0.role().is_routable_role()
    }

    #[getter]
    fn is_internal(&self) -> bool {
        self.0.is_internal()
    }

    #[getter]
    fn copper_thickness_mm(&self) -> f64 {
        self.0.copper_thickness_mm()
    }

    #[getter]
    fn copper_weight_oz(&self) -> f64 {
        self.0.copper_weight_oz()
    }

    fn __repr__(&self) -> String {
        format!(
            "Layer(name={:?}, role={:?}, internal={}, copper_weight_oz={})",
            self.0.name(),
            self.0.role().as_str(),
            self.0.is_internal(),
            self.0.copper_weight_oz()
        )
    }

    fn __eq__(&self, other: &PyLayer) -> bool {
        self.0 == other.0
    }
}

/// Return declared copper layer roles without requiring stackup thickness.
/// This is the production boundary for architecture consumers such as
/// `board_layer_roles.py`; use [`Stackup::parse`] in Rust when copper weight
/// is needed.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "parse_declared_layer_roles")]
pub fn parse_declared_layer_roles_py(pcb_content: String) -> PyResult<Vec<(String, String)>> {
    temper_py_bridge::catch_unwind(|| -> PyResult<Vec<(String, String)>> {
        parse_declared_layer_roles(&pcb_content)
            .map(|layers| {
                layers
                    .into_iter()
                    .map(|(name, role)| (name, role.as_str().to_string()))
                    .collect()
            })
            .map_err(|e| PyValueError::new_err(e.to_string()))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

/// The router engine's real signal-layer coverage today, as an ordered
/// list of names — the single Rust-side copy of
/// [`ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES`]. `board_layer_roles.py` should
/// read this rather than hold its own `tuple[str, ...]` literal.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "engine_supported_signal_layer_names")]
pub fn engine_supported_signal_layer_names_py() -> Vec<String> {
    ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES.iter().map(|s| s.to_string()).collect()
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyLayer>()?;
    m.add_function(wrap_pyfunction!(parse_declared_layer_roles_py, m)?)?;
    m.add_function(wrap_pyfunction!(engine_supported_signal_layer_names_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// A minimal, real-shaped 6-layer board: F.Cu/In3.Cu/In4.Cu/B.Cu
    /// signal, In1.Cu/In2.Cu power -- the PR #1178 stackup this module's
    /// doc comment references. 2oz outer (0.070mm), 1oz inner (0.035mm).
    const SIX_LAYER_BOARD: &str = r#"
        (kicad_pcb
          (layers
            (0 "F.Cu" signal)
            (1 "In1.Cu" power)
            (2 "In2.Cu" power)
            (3 "In3.Cu" signal)
            (4 "In4.Cu" signal)
            (31 "B.Cu" signal)
            (32 "B.Adhes" user "B.Adhesive")
          )
          (setup
            (stackup
              (layer "F.Cu" (type "copper") (thickness 0.070))
              (layer "In1.Cu" (type "copper") (thickness 0.035))
              (layer "In2.Cu" (type "copper") (thickness 0.035))
              (layer "In3.Cu" (type "copper") (thickness 0.035))
              (layer "In4.Cu" (type "copper") (thickness 0.035))
              (layer "B.Cu" (type "copper") (thickness 0.070))
            )
          )
        )
    "#;

    /// The pre-2026-08-13 2-layer board -- the shape that must ALSO parse
    /// correctly, since nothing about this parser is 6-layer-specific.
    const TWO_LAYER_BOARD: &str = r#"
        (kicad_pcb
          (layers
            (0 "F.Cu" signal)
            (31 "B.Cu" signal)
          )
          (setup
            (stackup
              (layer "F.Cu" (type "copper") (thickness 0.070))
              (layer "B.Cu" (type "copper") (thickness 0.070))
            )
          )
        )
    "#;

    #[cfg_attr(test, test)]
    fn parses_six_layer_board_roles_and_positions() {
        let stackup = Stackup::parse(SIX_LAYER_BOARD).unwrap();
        assert_eq!(stackup.layers().len(), 6);

        let f_cu = stackup.layer("F.Cu").unwrap();
        assert_eq!(f_cu.role(), LayerRole::Signal);
        assert_eq!(f_cu.position(), LayerPosition::Outer);
        assert!(!f_cu.is_internal());

        let b_cu = stackup.layer("B.Cu").unwrap();
        assert_eq!(b_cu.role(), LayerRole::Signal);
        assert_eq!(b_cu.position(), LayerPosition::Outer);

        for inner in ["In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"] {
            let l = stackup.layer(inner).unwrap();
            assert_eq!(l.position(), LayerPosition::Inner, "{inner} must be Inner");
            assert!(l.is_internal());
        }

        assert_eq!(stackup.layer("In1.Cu").unwrap().role(), LayerRole::Power);
        assert_eq!(stackup.layer("In3.Cu").unwrap().role(), LayerRole::Signal);
    }

    #[cfg_attr(test, test)]
    fn copper_weight_derived_from_declared_thickness() {
        let stackup = Stackup::parse(SIX_LAYER_BOARD).unwrap();
        // 2oz outer: 0.070mm / 0.035mm/oz == 2.0oz.
        assert_eq!(stackup.layer("F.Cu").unwrap().copper_weight_oz(), 2.0);
        assert_eq!(stackup.layer("B.Cu").unwrap().copper_weight_oz(), 2.0);
        // 1oz inner: 0.035mm / 0.035mm/oz == 1.0oz.
        assert_eq!(stackup.layer("In3.Cu").unwrap().copper_weight_oz(), 1.0);
        assert_eq!(stackup.layer("In4.Cu").unwrap().copper_weight_oz(), 1.0);
        assert_eq!(
            copper_weight_oz_for(stackup.layer("In1.Cu").unwrap()),
            1.0
        );
    }

    /// THE regression test: on the 6-layer board, `signal_layers()`
    /// reflects all four declared signal layers automatically -- there is
    /// no second hardcoded pair anywhere in this module for it to have
    /// stayed frozen against. This is what "stale copy no longer
    /// type-checks" means operationally: changing the INPUT TEXT is the
    /// only way to change the output; there is no parallel constant that
    /// could disagree with it.
    #[cfg_attr(test, test)]
    fn six_layer_declaration_widens_signal_layers_with_no_separate_copy_to_go_stale() {
        let stackup = Stackup::parse(SIX_LAYER_BOARD).unwrap();
        let names: Vec<&str> = stackup.signal_layers().map(|l| l.name()).collect();
        assert_eq!(names, vec!["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]);
    }

    #[cfg_attr(test, test)]
    fn two_layer_board_still_parses() {
        let stackup = Stackup::parse(TWO_LAYER_BOARD).unwrap();
        let names: Vec<&str> = stackup.signal_layers().map(|l| l.name()).collect();
        assert_eq!(names, vec!["F.Cu", "B.Cu"]);
        assert_eq!(stackup.layer("F.Cu").unwrap().position(), LayerPosition::Outer);
        assert_eq!(stackup.layer("B.Cu").unwrap().position(), LayerPosition::Outer);
    }

    #[cfg_attr(test, test)]
    fn routable_signal_layers_intersects_declaration_with_engine_capability() {
        let stackup = Stackup::parse(SIX_LAYER_BOARD).unwrap();
        let names: Vec<&str> =
            stackup.routable_signal_layers().into_iter().map(|l| l.name()).collect();
        // Engine capability today is exactly the declared signal set, so
        // this equals signal_layers() -- but goes through the intersection,
        // not a second copy of the pair.
        assert_eq!(names, vec!["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]);
    }

    #[cfg_attr(test, test)]
    fn missing_layers_block_fails_closed() {
        let err = Stackup::parse("(kicad_pcb (setup (stackup)))").unwrap_err();
        assert_eq!(err, StackupParseError::NoLayersBlock);
    }

    #[cfg_attr(test, test)]
    fn missing_stackup_block_fails_closed() {
        let text = r#"(kicad_pcb (layers (0 "F.Cu" signal) (31 "B.Cu" signal)))"#;
        let err = Stackup::parse(text).unwrap_err();
        assert_eq!(err, StackupParseError::NoStackupBlock);
    }

    #[cfg_attr(test, test)]
    fn declared_layer_with_no_thickness_entry_fails_closed() {
        let text = r#"
            (kicad_pcb
              (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
              (setup (stackup (layer "F.Cu" (type "copper") (thickness 0.070))))
            )
        "#;
        let err = Stackup::parse(text).unwrap_err();
        assert_eq!(err, StackupParseError::MissingCopperThickness("B.Cu".to_string()));
    }

    #[cfg_attr(test, test)]
    fn no_recognized_copper_layer_fails_closed() {
        let text = r#"(kicad_pcb (layers (0 "F.SilkS" user)) (setup (stackup)))"#;
        let err = Stackup::parse(text).unwrap_err();
        assert_eq!(err, StackupParseError::NoRecognizedCopperLayer);
    }

    #[cfg_attr(test, test)]
    fn test_only_escape_hatch_derives_position_from_order() {
        let stackup = Stackup::test_only(vec![
            TestOnlyLayerSpec {
                name: "F.Cu".to_string(),
                role: LayerRole::Signal,
                copper_thickness_mm: 0.070,
            },
            TestOnlyLayerSpec {
                name: "In1.Cu".to_string(),
                role: LayerRole::Power,
                copper_thickness_mm: 0.035,
            },
            TestOnlyLayerSpec {
                name: "B.Cu".to_string(),
                role: LayerRole::Signal,
                copper_thickness_mm: 0.070,
            },
        ]);
        assert_eq!(stackup.layer("F.Cu").unwrap().position(), LayerPosition::Outer);
        assert_eq!(stackup.layer("In1.Cu").unwrap().position(), LayerPosition::Inner);
        assert_eq!(stackup.layer("B.Cu").unwrap().position(), LayerPosition::Outer);
        assert_eq!(stackup.layer("F.Cu").unwrap().copper_weight_oz(), 2.0);
    }

    #[cfg_attr(test, test)]
    fn layer_role_is_routable_role() {
        assert!(LayerRole::Signal.is_routable_role());
        assert!(LayerRole::Mixed.is_routable_role());
        assert!(!LayerRole::Power.is_routable_role());
        assert!(!LayerRole::Jumper.is_routable_role());
    }

    #[cfg_attr(test, test)]
    fn engine_supported_signal_layer_names_is_the_single_copy() {
        assert_eq!(
            ENGINE_SUPPORTED_SIGNAL_LAYER_NAMES,
            &["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("layer_identity::tests::parses_six_layer_board_roles_and_positions", parses_six_layer_board_roles_and_positions),
        ("layer_identity::tests::copper_weight_derived_from_declared_thickness", copper_weight_derived_from_declared_thickness),
        ("layer_identity::tests::six_layer_declaration_widens_signal_layers_with_no_separate_copy_to_go_stale", six_layer_declaration_widens_signal_layers_with_no_separate_copy_to_go_stale),
        ("layer_identity::tests::two_layer_board_still_parses", two_layer_board_still_parses),
        ("layer_identity::tests::routable_signal_layers_intersects_declaration_with_engine_capability", routable_signal_layers_intersects_declaration_with_engine_capability),
        ("layer_identity::tests::missing_layers_block_fails_closed", missing_layers_block_fails_closed),
        ("layer_identity::tests::missing_stackup_block_fails_closed", missing_stackup_block_fails_closed),
        ("layer_identity::tests::declared_layer_with_no_thickness_entry_fails_closed", declared_layer_with_no_thickness_entry_fails_closed),
        ("layer_identity::tests::no_recognized_copper_layer_fails_closed", no_recognized_copper_layer_fails_closed),
        ("layer_identity::tests::test_only_escape_hatch_derives_position_from_order", test_only_escape_hatch_derives_position_from_order),
        ("layer_identity::tests::layer_role_is_routable_role", layer_role_is_routable_role),
        ("layer_identity::tests::engine_supported_signal_layer_names_is_the_single_copy", engine_supported_signal_layer_names_is_the_single_copy),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
