// The portable cardinality compute of `router_v6/stage_ledger.py` (the last
// portable router_v6 orchestration module — after this, only presentation /
// test tooling and the ortools boundary remain in router_v6 Python).
//
// Rust Orchestration Engine plan 2026-08-09-001, the final router_v6
// orchestration slice: the pre-migration module's deterministic logic —
// `_snapshot` (the per-object cardinality counting over duck-typed
// BoardState / ParsedPCB / routing-result shapes) and `_diff` (the
// five-field count comparison) — moves here as the `snapshot_cardinality` /
// `diff_cardinality` pyfunctions plus the `CardinalitySnapshot` pyclass (the
// pre-migration `_CardinalitySnapshot` dataclass). The pre-migration module
// is pinned VERBATIM as `tests/router_v6/_stage_ledger_py_oracle.py`
// (content-hash registered in `scripts/oracle_hashes.json`; the differential
// `tests/router_v6/test_stage_ledger_rust_differential.py` pins bit-identical
// field/repr/str parity).
//
// What stays Python (the shim, `router_v6/stage_ledger.py`): the stateful
// orchestration — the `StageLedger` state machine (`_pre`/`_post` snapshot
// storage, the `checkin`/`checkout`/`verify` flow, the `fail_on_imbalance`
// raise decision and the logger emission) — and the presentation:
// `LedgerReport` + its `__str__`, the checkout message rendering (the
// human-readable rendering of the diff list, the same family as
// `LedgerReport.__str__`), and the `StageLedgerImbalanceError` exception
// class (exceptions stay Python per the crate-wide convention). The
// `_pipeline_core.py` production caller is untouched.
//
// Bit-exactness traps pinned here:
// - `hasattr` swallows only `AttributeError`; any other exception from a
//   probe (`has_attr`) propagates exactly like CPython's `hasattr`.
// - `if state_or_pcb.channel_skeletons:` is a TRUTHINESS test, not a
//   `is not None` test; `escape_vias = getattr(...) or ()` is a truthiness
//   fallback too — both are replicated with `PyAny::is_truthy()`, so a
//   custom `__bool__` on the attribute value behaves identically.
// - `isinstance(val, dict)` is subtype-aware (`PyObject_TypeCheck`), so a
//   dict subclass in `routing_spaces` is still counted.
// - `max(0, len(path.coordinates) - 1)` for a zero-length coordinates list
//   is `len().saturating_sub(1)` in Rust (Python's negative result clamps
//   to zero).
// - `len(x)` on any sized object goes through `PyObject_Size`, i.e. Python
//   `__len__`, exactly like the oracle's `len()`.

#[cfg(feature = "python")]
use pyo3::exceptions::PyAttributeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "python")]
use crate::grid_hv::getattr_default;

/// The five cardinality field names in the oracle's fixed iteration order
/// (the order `_diff` reports and the shim's message rendering preserves).
const FIELD_NAMES: [&str; 5] = [
    "net_count",
    "component_count",
    "channel_count",
    "via_count",
    "segment_count",
];

/// Pure five-field count comparison (the `_diff` kernel).
///
/// Returns `(field, before, after)` for every field whose count changed,
/// in the fixed `FIELD_NAMES` order. The exported `diff_cardinality`
/// pyfunction (which the shim wires) is the thin `Bound`-to-array adapter
/// over this; keeping the kernel here as a plain `fn` lets it be unit-tested
/// without a Python interpreter (the crate's pure-helper pattern, as in
/// `timing.rs`'s `py_max`/`py_cmp`).
fn diff_counts(pre: [usize; 5], post: [usize; 5]) -> Vec<(String, usize, usize)> {
    let mut diffs = Vec::new();
    for (i, name) in FIELD_NAMES.iter().enumerate() {
        if pre[i] != post[i] {
            diffs.push((name.to_string(), pre[i], post[i]));
        }
    }
    diffs
}

/// Mirror of Python `router_v6.stage_ledger._CardinalitySnapshot` (dataclass).
///
/// The five tracked object counts, all defaulting to 0. `__repr__` and
/// `__eq__` reproduce the dataclass's shapes bit-for-bit (the class name the
/// dataclass repr prints is `_CardinalitySnapshot`, preserved literally).
#[cfg(feature = "python")]
#[pyclass(
    dict,
    skip_from_py_object,
    module = "temper_orchestration",
    name = "CardinalitySnapshot"
)]
#[derive(Clone, Debug, Default)]
pub struct CardinalitySnapshot {
    #[pyo3(get, set)]
    pub net_count: usize,
    #[pyo3(get, set)]
    pub component_count: usize,
    #[pyo3(get, set)]
    pub channel_count: usize,
    #[pyo3(get, set)]
    pub via_count: usize,
    #[pyo3(get, set)]
    pub segment_count: usize,
}

#[cfg(feature = "python")]
#[pymethods]
impl CardinalitySnapshot {
    #[new]
    #[pyo3(signature = (net_count=0, component_count=0, channel_count=0, via_count=0, segment_count=0))]
    fn new(
        net_count: usize,
        component_count: usize,
        channel_count: usize,
        via_count: usize,
        segment_count: usize,
    ) -> Self {
        Self {
            net_count,
            component_count,
            channel_count,
            via_count,
            segment_count,
        }
    }

    /// Dataclass repr: `_CardinalitySnapshot(net_count=0, ...)`.
    fn __repr__(&self) -> String {
        format!(
            "_CardinalitySnapshot(net_count={}, component_count={}, channel_count={}, \
             via_count={}, segment_count={})",
            self.net_count,
            self.component_count,
            self.channel_count,
            self.via_count,
            self.segment_count,
        )
    }

    /// Dataclass equality: same type + all five counts equal.
    fn __eq__(&self, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Self>() {
            return Ok(false);
        }
        let rhs = other.cast::<Self>()?.borrow();
        Ok(self.net_count == rhs.net_count
            && self.component_count == rhs.component_count
            && self.channel_count == rhs.channel_count
            && self.via_count == rhs.via_count
            && self.segment_count == rhs.segment_count)
    }
}

#[cfg(feature = "python")]
/// CPython `hasattr(obj, name)`: True on attribute presence, False on
/// `AttributeError`, and every OTHER exception propagates (CPython's
/// `hasattr` swallows only `AttributeError`).
fn has_attr(py: Python<'_>, obj: &Bound<'_, PyAny>, name: &str) -> PyResult<bool> {
    match obj.getattr(name) {
        Ok(_) => Ok(true),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(false),
        Err(e) => Err(e),
    }
}

#[cfg(feature = "python")]
/// The pre-migration `_snapshot`: extract the five cardinality counts from a
/// BoardState (`_parsed_pcb` + `channel_skeletons` + `_escape_vias`), a
/// ParsedPCB (`nets`/`components` + `routing_spaces` channels), or a pipeline
/// result object (`routing_results.compiled_routes` path segments).
#[pyfunction]
pub fn snapshot_cardinality(
    py: Python<'_>,
    state_or_pcb: &Bound<'_, PyAny>,
) -> PyResult<CardinalitySnapshot> {
    let mut snap = CardinalitySnapshot::default();

    // BoardState (temper_placer.deterministic.state)
    if has_attr(py, state_or_pcb, "_parsed_pcb")? {
        let pcb = state_or_pcb.getattr("_parsed_pcb")?;
        if !pcb.is_none() {
            if has_attr(py, &pcb, "nets")? {
                snap.net_count = pcb.getattr("nets")?.len()?;
            }
            if has_attr(py, &pcb, "components")? {
                snap.component_count = pcb.getattr("components")?.len()?;
            }
        }
        // Python `if state_or_pcb.channel_skeletons:` is a truthiness test;
        // the oracle then iterates `channel_skeletons.values()`.
        let skeletons = state_or_pcb.getattr("channel_skeletons")?;
        if skeletons.is_truthy()? {
            let mut channel_count: usize = 0;
            let values = skeletons.getattr("values")?.call0()?;
            for s in values.try_iter()? {
                let skeleton = s?;
                let channels = getattr_default(py, &skeleton, "channels", empty_list(py))?;
                channel_count += channels.len()?;
            }
            snap.channel_count = channel_count;
        }
        // Python `getattr(state_or_pcb, "_escape_vias", None) or ()`.
        let escape_vias = getattr_default(py, state_or_pcb, "_escape_vias", py.None())?;
        let via_src: Bound<'_, PyAny> = if escape_vias.is_truthy()? {
            escape_vias
        } else {
            PyTuple::empty(py).into_any()
        };
        snap.via_count = via_src.len()?;
        return Ok(snap);
    }

    // ParsedPCB
    if has_attr(py, state_or_pcb, "nets")? {
        snap.net_count = state_or_pcb.getattr("nets")?.len()?;
    }
    if has_attr(py, state_or_pcb, "components")? {
        snap.component_count = state_or_pcb.getattr("components")?.len()?;
    }

    // Channel dicts (routing_spaces) — the oracle iterates `val.values()`.
    let routing_spaces = getattr_default(py, state_or_pcb, "routing_spaces", py.None())?;
    if routing_spaces.is_instance_of::<PyDict>() {
        let mut channel_count = snap.channel_count;
        let values = routing_spaces.getattr("values")?.call0()?;
        for v in values.try_iter()? {
            let val = v?;
            if has_attr(py, &val, "channels")? {
                channel_count += val.getattr("channels")?.len()?;
            }
        }
        snap.channel_count = channel_count;
    }

    // Segment count from routing results — the oracle iterates
    // `results.compiled_routes.values()`.
    let results = getattr_default(py, state_or_pcb, "routing_results", py.None())?;
    if !results.is_none() && has_attr(py, &results, "compiled_routes")? {
        let compiled = results.getattr("compiled_routes")?;
        let mut segment_count = snap.segment_count;
        let values = compiled.getattr("values")?.call0()?;
        for r in values.try_iter()? {
            let route = r?;
            let path = getattr_default(py, &route, "path", py.None())?;
            if has_attr(py, &path, "segments")? {
                segment_count += path.getattr("segments")?.len()?;
            } else if has_attr(py, &path, "coordinates")? {
                segment_count += path.getattr("coordinates")?.len()?.saturating_sub(1);
            }
        }
        snap.segment_count = segment_count;
    }

    Ok(snap)
}

#[cfg(feature = "python")]
/// The pre-migration `_diff`: compare two cardinality snapshots and return
/// the list of `(field, before, after)` for every count that changed, in the
/// fixed field order.
#[pyfunction]
pub fn diff_cardinality(
    pre: &Bound<'_, CardinalitySnapshot>,
    post: &Bound<'_, CardinalitySnapshot>,
) -> Vec<(String, usize, usize)> {
    let p = pre.borrow();
    let q = post.borrow();
    diff_counts(
        [
            p.net_count,
            p.component_count,
            p.channel_count,
            p.via_count,
            p.segment_count,
        ],
        [
            q.net_count,
            q.component_count,
            q.channel_count,
            q.via_count,
            q.segment_count,
        ],
    )
}

#[cfg(feature = "python")]
fn empty_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn diff_counts_identical_snapshots_are_balanced() {
        assert!(diff_counts([0, 0, 0, 0, 0], [0, 0, 0, 0, 0]).is_empty());
        assert!(diff_counts([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]).is_empty());
    }

    #[test]
    fn diff_counts_reports_changed_fields_in_fixed_order() {
        let diffs = diff_counts([1, 2, 3, 4, 5], [1, 9, 3, 0, 7]);
        assert_eq!(
            diffs,
            vec![
                ("component_count".to_string(), 2, 9),
                ("via_count".to_string(), 4, 0),
                ("segment_count".to_string(), 5, 7),
            ]
        );
    }

    #[test]
    fn diff_counts_all_fields_changed_reports_every_one() {
        let diffs = diff_counts([0, 0, 0, 0, 0], [1, 2, 3, 4, 5]);
        assert_eq!(
            diffs,
            vec![
                ("net_count".to_string(), 0, 1),
                ("component_count".to_string(), 0, 2),
                ("channel_count".to_string(), 0, 3),
                ("via_count".to_string(), 0, 4),
                ("segment_count".to_string(), 0, 5),
            ]
        );
    }

    #[test]
    fn diff_counts_swapping_arms_flips_before_after() {
        let a = [1, 2, 3, 4, 5];
        let b = [1, 9, 3, 0, 7];
        let forward = diff_counts(a, b);
        let backward = diff_counts(b, a);
        assert_eq!(forward.len(), backward.len());
        for ((fn_a, before, after), (fn_b, b_before, b_after)) in forward.iter().zip(&backward) {
            assert_eq!(fn_a, fn_b);
            assert_eq!(before, b_after);
            assert_eq!(after, b_before);
        }
    }

    #[test]
    fn repr_matches_dataclass_shape_bit_for_bit() {
        Python::initialize();
        Python::attach(|py| {
            let snap = Py::new(py, CardinalitySnapshot::default()).unwrap();
            let repr: String = snap
                .bind(py)
                .call_method0("__repr__")
                .unwrap()
                .extract()
                .unwrap();
            assert_eq!(
                repr,
                "_CardinalitySnapshot(net_count=0, component_count=0, channel_count=0, \
                 via_count=0, segment_count=0)"
            );
        });
    }

    #[test]
    fn eq_matches_dataclass_equality() {
        Python::initialize();
        Python::attach(|py| {
            let a = Py::new(
                py,
                CardinalitySnapshot {
                    net_count: 1,
                    component_count: 2,
                    channel_count: 3,
                    via_count: 4,
                    segment_count: 5,
                },
            )
            .unwrap();
            let same = Py::new(
                py,
                CardinalitySnapshot {
                    net_count: 1,
                    component_count: 2,
                    channel_count: 3,
                    via_count: 4,
                    segment_count: 5,
                },
            )
            .unwrap();
            let diff = Py::new(
                py,
                CardinalitySnapshot {
                    net_count: 1,
                    component_count: 2,
                    channel_count: 3,
                    via_count: 4,
                    segment_count: 9,
                },
            )
            .unwrap();
            assert!(a.bind(py).eq(same.bind(py)).unwrap());
            assert!(!a.bind(py).eq(diff.bind(py)).unwrap());
        });
    }
}
