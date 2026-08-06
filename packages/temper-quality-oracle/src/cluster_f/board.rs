//! The parsed-board view the three cluster-F modules read.
//!
//! The pinned kernels touch a small, fixed set of attributes on the parser's
//! `ParseResult` (the table is in
//! `packages/temper-placer/tests/router_v6/_quality_metrics_fixtures.py`).
//! This is that set and nothing more, so a synthetic scenario and a real
//! `.kicad_pcb` parse reach the kernels through one type.

/// A coordinate as the *Python object* the parser produced.
///
/// `parse_kicad_pcb` yields a mix: on `bitaxe_ultra` 5 of 3,732 trace
/// coordinates, 3 of 402 via coordinates and 6 of 933 trace widths come back as
/// Python **ints**, not floats. The linters echo those objects straight into a
/// finding's `position`, and the differential's `sig()` records
/// `type(v).__name__` at every leaf — so collapsing `100` to `100.0` is a
/// visible divergence, and one that only the real corpus reaches.
///
/// Arithmetic always goes through [`Num::f`]; the variant is carried purely so
/// an echoed coordinate keeps its type. `int` values in board coordinates are
/// far below 2**53, so the widening is exact.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Num {
    Int(i64),
    Float(f64),
}

impl Num {
    #[inline]
    pub fn f(self) -> f64 {
        match self {
            Num::Int(i) => i as f64,
            Num::Float(x) => x,
        }
    }
}

/// A point whose two coordinates keep their Python types.
pub type Point = (Num, Num);

/// The f64 pair the geometry kernels operate on.
#[inline]
pub fn pf(p: Point) -> (f64, f64) {
    (p.0.f(), p.1.f())
}

/// A routed track segment. `net` is `None` for an unnamed trace, which is a
/// different value from `Some("")` at the `trace.net != via.net` comparison in
/// `lint_isolated_vias` but the same bucket under `trace.net or "_unnamed"`.
#[derive(Clone, Debug)]
pub struct Trace {
    pub start: Point,
    pub end: Point,
    pub width: Num,
    pub layer: String,
    pub net: Option<String>,
}

#[derive(Clone, Debug)]
pub struct Via {
    pub position: Point,
    pub net: Option<String>,
}

/// `initial_position` is **board-relative**, while [`Trace::start`] / `end`
/// are page-absolute KiCad coordinates. The corridor kernels compare the two
/// frames directly; see defect 2 in the oracle header. That is reproduced, not
/// repaired.
#[derive(Clone, Debug)]
pub struct Component {
    pub reference: String,
    pub initial_position: Option<(f64, f64)>,
    pub width: f64,
    pub height: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct Board {
    pub width: f64,
    pub height: f64,
}

#[derive(Clone, Debug, Default)]
pub struct ParseView {
    pub traces: Vec<Trace>,
    pub vias: Vec<Via>,
    pub components: Vec<Component>,
    pub board: Option<Board>,
    /// `router_v6.net_classification._SINGLE_LAYER_MODE`, sampled at call
    /// time. It is a module-global read by `is_ground_net`, i.e. a hidden
    /// input to `_classify_vias`; carrying it on the view keeps it explicit.
    pub single_layer_mode: bool,
}

/// The `{"start": ..., "end": ..., "width": ..., "layer": ...}` dict
/// `_load_traces_by_net` produces and `_order_traces` consumes.
#[derive(Clone, Debug)]
pub struct TraceRecord {
    pub start: Point,
    pub end: Point,
    pub width: Num,
    pub layer: String,
}

/// `_load_traces_by_net`: traces grouped by `trace.net or "_unnamed"`, in
/// **parser order**.
///
/// The returned order is the order in which each net was first seen. That is
/// a value, not a presentation detail: `lint_*` iterate this map directly, so
/// finding order tracks it. Nothing here sorts, and nothing here iterates a
/// hash map — the index map is used for lookup only.
pub fn load_traces_by_net(view: &ParseView) -> Vec<(String, Vec<TraceRecord>)> {
    let mut order: Vec<(String, Vec<TraceRecord>)> = Vec::new();
    let mut index: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for trace in &view.traces {
        let net_name = match &trace.net {
            Some(n) if !n.is_empty() => n.clone(),
            _ => "_unnamed".to_string(),
        };
        let record = TraceRecord {
            start: trace.start,
            end: trace.end,
            width: trace.width,
            layer: trace.layer.clone(),
        };
        match index.get(&net_name) {
            Some(&i) => order[i].1.push(record),
            None => {
                index.insert(net_name.clone(), order.len());
                order.push((net_name, vec![record]));
            }
        }
    }
    order
}
