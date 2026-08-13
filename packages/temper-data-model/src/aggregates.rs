//! The U3 (O-C3) owned AGGREGATE structs: [`Board`] + [`Netlist`], composing
//! the U2 leaves (`Component`/`Pin`/`Net`/`Val`).
//!
//! # Field classification (owned vs keep)
//!
//! The pyclasses these mirror (`board_contracts.Board`,
//! `netlist_contracts.Netlist`) perform **no `__init__` coercion** — the
//! pre-migration dataclasses store whatever the caller passes, and the
//! pyclass `__new__` stores it raw (`v.clone().unbind()`, see
//! `board_contracts.rs`). So every scalar field whose annotation says
//! `float` can in fact hold `int` — `Board(100, 80)`,
//! `Board.from_polygon` with int polygon coordinates (width/height are
//! `x_max - x_min`, type-preserving), and `keepouts=[(0, 0, 50, 80)]` are
//! all legal, and downstream consumers explicitly float-coerce
//! (`validation/geometric.py:289` does `tuple(float(v) for v in k)`).
//! Per the U0 concrete-Python-type discipline ("any field that can be
//! int-or-float uses [`Val`], never a widened `f64`"), these fields are
//! `Val`-shaped, so `1` stays `1` and `1.0` stays `1.0`.
//!
//! The fields that are NOT owned (foreign pyclasses, shapely geometry,
//! numpy arrays) are deliberately ABSENT from this crate's structs: this
//! crate is pyo3-free by construction (the wasm32 tier compiles it), so it
//! cannot hold `Py<PyAny>`. They are the orchestration-side `Marshal`'s
//! `Plain::Opaque` keeps — identity-preserved passthroughs that live on the
//! pyo3 side of the boundary (see `netlist_owned.rs`'s `OwnedBoard` and the
//! U3 section of `packages/temper-orchestration/VERIFICATION.md`).
//!
//! | Field | Owned type | Why |
//! |---|---|---|
//! | `Board.width` / `Board.height` | `Val` | no-coercion contract: `Board(100, 80)` and `Board.from_polygon(int coords)` produce ints; `Val` records which |
//! | `Board.origin` | `(Val, Val)` | `tuple[float, float]` raw-stored; int-shaped `(0, 0)` legal |
//! | `Board.keepouts` | `Vec<(Val, Val, Val, Val)>` | `list[tuple[float, float, float, float]]` raw-stored; consumers float-coerce → ints occur |
//! | `Board.zones` | *keep* | `list[Zone]` — foreign pyclass, ported by a later unit |
//! | `Board.mounting_holes` | *keep* | `list[MountingHole]` — foreign pyclass |
//! | `Board.ground_domains` | *keep* | `list[GroundDomain]` — foreign pyclass |
//! | `Board.layer_stackup` | *keep* | `LayerStackup | None` — foreign pyclass |
//! | `Board.outline_polygon` | *keep* | the outline geometry — consumed as shapely (`hv_lv_partition.py` `Polygon(p)`, `guard_strip.py`); identity passthrough is lossless for both the list form and a shapely form |
//! | `Board._zone_map` | *derived* | `dict[str, Zone]` recomputed by `__post_init__` from `zones`; `init=False` so it is never constructor-passed; its values are keeps anyway |
//! | `Netlist.components` | `Vec<Component>` | the U2 leaf |
//! | `Netlist.nets` | `Vec<Net>` | the U2 leaf |
//! | `Netlist._component_index` / `_net_index` / `_component_nets` | *derived* | recomputed by `__post_init__`/`build_indices` unconditionally from components/nets (a pure function); `repr=False` so they never appear in `__repr__`; `compare=True` so `==` needs them — recomputed identically on write-back |

use crate::{Component, Net, Val};

/// The owned aggregate mirroring `board_contracts.Board`'s OWNED fields.
///
/// See the module doc's field table for the owned-vs-keep classification and
/// the `Val` rationale (the pyclass raw-stores every constructor argument, so
/// `width`/`height`/`origin`/`keepouts` leaves can be `int` OR `float`).
///
/// `PartialEq` (not `Eq`) deliberately: `Val::Float` may hold a NaN.
#[derive(Clone, Debug, PartialEq)]
pub struct Board {
    pub width: Val,
    pub height: Val,
    pub origin: (Val, Val),
    pub keepouts: Vec<(Val, Val, Val, Val)>,
}

/// The owned aggregate mirroring `netlist_contracts.Netlist`'s OWNED fields.
///
/// The three `_`-prefixed index dicts (`_component_index`, `_net_index`,
/// `_component_nets`) are DERIVED, not stored: `__post_init__`/
/// `build_indices` recompute them unconditionally from `components`/`nets`
/// (a pure function of the two lists in order), `repr=False` excludes them
/// from `__repr__`, and the write-back constructor recomputes them
/// identically — so an owned struct holding only the two lists round-trips
/// the full pyclass bit-identically (type, repr and `==`).
#[derive(Clone, Debug, PartialEq)]
pub struct Netlist {
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// The aggregate `Val`-shaping is the int-vs-float distinction made a
    /// *type* at the aggregate level: `Board { width: Val::Int(100) }` must
    /// NOT equal a widened `Val::Float(100.0)`, or a `100` → `100.0` widen
    /// would be `==`-indistinguishable (the whole point of `Val`).
    #[test]
    fn board_vals_distinguish_int_from_float() {
        let int_board = Board {
            width: Val::Int(100),
            height: Val::Int(80),
            origin: (Val::Int(0), Val::Int(0)),
            keepouts: vec![(Val::Int(0), Val::Int(0), Val::Int(50), Val::Int(80))],
        };
        let float_board = Board {
            width: Val::Float(100.0),
            height: Val::Float(80.0),
            origin: (Val::Float(0.0), Val::Float(0.0)),
            keepouts: vec![(Val::Float(0.0), Val::Float(0.0), Val::Float(50.0), Val::Float(80.0))],
        };
        assert_ne!(int_board, float_board, "int 100 must not equal float 100.0");
        assert_eq!(int_board, int_board.clone());
        assert_eq!(float_board, float_board.clone());
    }

    /// The aggregate holds the U2 leaves: `Netlist.components` is the same
    /// `Component` the leaf unit defined, `Netlist.nets` the same `Net`.
    #[test]
    fn netlist_holds_the_u2_leaves() {
        let netlist = Netlist {
            components: vec![Component {
                ref_: "R1".into(),
                footprint: "fp".into(),
                bounds: vec![Val::Int(1), Val::Int(2)],
                pins: Vec::new(),
                net_class: "Signal".into(),
                zone: None,
                fixed: false,
                initial_position: None,
                initial_rotation_quadrant: None,
                initial_side: None,
                attributes: Vec::new(),
                tags: Vec::new(),
                sheetpath: None,
            }],
            nets: Vec::new(),
        };
        assert_eq!(netlist.components[0].ref_, "R1");
        assert_eq!(netlist.components[0].bounds, vec![Val::Int(1), Val::Int(2)]);
        assert!(netlist.nets.is_empty());
    }
}
