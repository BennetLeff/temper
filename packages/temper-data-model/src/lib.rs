//! Pure-Rust owned data model for the orchestration data-model port (unit
//! O-C3/U2).
//!
//! This crate is the home of the OWNED leaf structs (`Component`/`Pin`/`Net`)
//! that later units (U3's `Board`/`Netlist` aggregates, U4's remaining fields)
//! compose into a full `CoreBoardState`. It carries **no pyo3 dependency** —
//! the structs here are plain Rust data, importable from the orchestration
//! pyo3 surface (which implements the `Marshal` boundary around them) and,
//! once O-C4 does the physical crate split, from the `wasm32-unknown-unknown`
//! tier. See `packages/temper-orchestration/VERIFICATION.md` (unit O-C3/U2)
//! for the crate-home decision and the field-by-field type rationale.
//!
//! # The `Val`/`Plain` convention (from unit O-C3/U0)
//!
//! The Python dataclasses these mirror (`temper_placer/core/netlist.py`,
//! pinned VERBATIM in `temper-design-bundle`'s pyclasses) perform **no
//! `__init__` coercion**: `Component("R1", "fp", (1, 2))` stores `int`
//! bounds, so `Component.width` returns `int` `1`, not `1.0`. A Rust field
//! typed `f64` would silently widen every such value, changing `repr`, `==`
//! and downstream numpy dtype promotion. The convention (established in
//! `temper-orchestration`'s `marshal.rs`, U0) is therefore:
//!
//! * [`Val`] — the canonical type for a scalar field that can hold `int` OR
//!   `float`; it records which one it was and round-trips it unchanged.
//!   Used for [`Component::bounds`], the one field the pipeline demonstrably
//!   populates with ints (see `netlist_contracts.rs:11-28` and
//!   `dense_package_detection.py:67`'s `bounds=(7, 7)` docstring).
//! * concrete Rust scalars (`String`/`bool`/`f64`/`i64`) — for fields whose
//!   contract type is unambiguous and whose real pipeline values are always
//!   that type. A `f64` field REJECTS an int-shaped value loudly (the U0
//!   "an int is not a float" discipline) rather than widening it.
//! * plain Rust collections — `Vec<(String, String)>` for an insertion-ordered
//!   `dict[str, str]` (`attributes`), `Vec<String>` for a `frozenset` read in
//!   iteration order (`tags`), `(f64, f64)` for the always-float
//!   `tuple[float, float]` fields (`position`, `initial_position`).
//!
//! `Plain` (the lossless nested-value tree with its `Opaque` passthrough for
//! numpy/shapely/foreign pyclasses) stays in `temper-orchestration`'s
//! `marshal.rs` — it is pyo3-shaped by construction and none of the leaf
//! structs here need it.

/// The concrete-Python-type canonical for a field that can hold `int` OR
/// `float` (e.g. a component's bounds `(1, 2)` vs `(1.0, 2.0)`).
///
/// Round-trips preserving WHICH it was — `extract::<f64>()` alone would
/// silently widen `int` `1` to `float` `1.0`, changing `repr` (`1` → `1.0`),
/// `==` against int-sensitive code, and downstream numpy dtype promotion.
///
/// `PartialEq` (not `Eq`) deliberately: `Float(f64)` may hold a NaN, which
/// breaks `Eq` reflexivity.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Val {
    Int(i64),
    Float(f64),
}

/// A pin on a component (mirrors `Pin` in `temper_placer/core/netlist.py`).
///
/// Field types: `position` is the always-float `tuple[float, float]` pin
/// offset (`(f64, f64)` — an int-shaped coordinate is a loud marshalling
/// error, per the U0 "an int is not a float" discipline); the float scalar
/// fields (`width`/`height`/`drill`/`roundrect_ratio`/`pad_rotation_deg`)
/// are concrete `f64` for the same reason. `net` is `Option<String>` (the
/// dataclass default is `None`, which is also a legal explicit value).
#[derive(Clone, Debug, PartialEq)]
pub struct Pin {
    pub name: String,
    pub number: String,
    pub position: (f64, f64),
    pub net: Option<String>,
    pub width: f64,
    pub height: f64,
    pub shape: String,
    pub layer: String,
    pub drill: f64,
    pub is_pth: bool,
    pub roundrect_ratio: f64,
    pub pad_rotation_deg: f64,
}

/// A component to be placed on the PCB (mirrors `Component` — the *netlist*
/// component, distinct from the board `Component`).
///
/// [`bounds`](Self::bounds) is `Vec<Val>`: the `(width, height)` tuple whose
/// elements the pipeline demonstrably writes as `int` OR `float` (the
/// concrete-Python-type hazard). Every other numeric field is concrete:
/// `initial_position` is `Option<(f64, f64)>` (the always-float
/// `tuple[float, float] | None`), `initial_rotation`/`initial_side` are
/// `Option<i64>` (`int | None`). `attributes` is an insertion-ordered
/// `dict[str, str]`; `tags` is a `frozenset` of strings read in iteration
/// order (a frozenset has no duplicates, so a `Vec` is faithful).
#[derive(Clone, Debug, PartialEq)]
pub struct Component {
    pub ref_: String,
    pub footprint: String,
    pub bounds: Vec<Val>,
    pub pins: Vec<Pin>,
    pub net_class: String,
    pub zone: Option<String>,
    pub fixed: bool,
    pub initial_position: Option<(f64, f64)>,
    pub initial_rotation: Option<i64>,
    pub initial_side: Option<i64>,
    pub attributes: Vec<(String, String)>,
    pub tags: Vec<String>,
    pub sheetpath: Option<String>,
}

/// An electrical net connecting multiple pins (mirrors `Net`).
///
/// `pins` is `Vec<(String, String)>`: the `list[tuple[str, str]]` of
/// `(component_ref, pin_name)` pairs (each pair a 2-tuple, the list
/// insertion-ordered). The float scalars `weight`/`max_current` are concrete
/// `f64` (their dataclass defaults are float literals and the pipeline always
/// passes floats).
#[derive(Clone, Debug, PartialEq)]
pub struct Net {
    pub name: String,
    pub pins: Vec<(String, String)>,
    pub net_class: String,
    pub weight: f64,
    pub max_current: f64,
    pub voltage_class: String,
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// `Val` is the int-vs-float distinction made a *type*: `Val::Int(1)`
    /// must NOT equal `Val::Float(1.0)`, or the whole point of the canonical
    /// type is lost (a widened `1` → `1.0` would then be `==`-indistinguishable).
    #[test]
    fn val_distinguishes_int_from_float() {
        assert_eq!(Val::Int(1), Val::Int(1));
        assert_eq!(Val::Float(1.0), Val::Float(1.0));
        assert_ne!(Val::Int(1), Val::Float(1.0), "int 1 must not equal float 1.0");
        assert_ne!(Val::Int(0), Val::Float(0.0), "int 0 must not equal float 0.0");
        // -0.0 vs 0.0 are equal as f64 (Python `-0.0 == 0.0`), so they are the
        // same Val — matching CPython float equality.
        assert_eq!(Val::Float(-0.0), Val::Float(0.0));
    }
}
