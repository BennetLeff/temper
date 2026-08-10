//! Phase-A U9 (rust-orchestration-engine plan) typed marshalling boundary
//! for the Rust loop extractor.
//!
//! Migrated from `temper_placer/core/loop_extractor_rs.py`, per the plan's
//! Phase-A table:
//!
//! | Python marshaler               | Rust type                    | Python name           |
//! |--------------------------------|------------------------------|-----------------------|
//! | `_netlist_to_dict`             | [`LoopExtractionInput`]      | `LoopExtractionInput` |
//! | `_dict_to_loop_collection`     | [`LoopExtractionOutput`]     | `LoopExtractionOutput`|
//!
//! `_netlist_to_dict` builds the flat dict that the
//! `temper_rust_router.auto_extract_loops_rust` JSON bridge consumes. After
//! Phase A the Python shim body collapses to
//! `LoopExtractionInput.from_netlist(...).to_json()` -- the dict-building
//! tax moves to Rust, exactly the U5 `DrcBoardSnapshot` /
//! U6 `OracleInput` pattern. The bridge signature itself (JSON string) is
//! in `temper-rust-router`, outside this unit's file ownership, so the
//! shim round-trips through `to_json()`; the kernel-signature tightening is
//! a later phase in that crate.
//!
//! `_dict_to_loop_collection` parses the bridge's output dict. The typed
//! [`LoopExtractionOutput`] carries the `ok`/`error`/`loops` wire surface
//! with the shim's documented defaults (missing `loops` -> empty, missing
//! `ok` -> `False`, per-loop `components`/`nets` -> `[]`, `loop_type` ->
//! `"unknown"`, `max_area_mm2` -> `500.0`, missing `name` -> `KeyError`).
//! The loop-type -> priority/events/return-path *reconstruction* stays in
//! the Python shim (it maps onto the `temper_placer.core.loop` Python-dataclass
//! enums, which are a different surface from this crate's `loops.rs`
//! pyclasses and are outside this unit's scope); the typed output makes the
//! wire parse total and is what the shim reads.
//!
//! # Bit-exactness notes
//!
//! - `to_dict()` inserts keys in the pre-migration dict order (components
//!   then nets; per component `ref`/`footprint`/`mpn`/`value`/`net_class`/
//!   `pins`; per pin `name`/`net`), so `json.dumps` of the result is
//!   byte-identical to the pre-migration `json.dumps(_netlist_to_dict(..))`.
//! - `to_json()` delegates to CPython `json.dumps` itself (the
//!   `hypergraph_contracts.rs` numpy precedent: the library produces the
//!   bytes), so separator/escape/ordering semantics are CPython's own.
//! - `net` is carried as `Option<String>`: `None` becomes JSON `null`
//!   (the bridge's `PinInput.net: Option<String>`), `""` stays `""`.
//! - The `net_class` component key is included in the wire even though the
//!   bridge ignores it (serde drops unknown fields): it is part of the
//!   byte-identical dict contract.
//!
//! # R19-style retained-oracle rule
//!
//! The pre-migration Python marshaler bodies are NOT kept here. They live
//! verbatim in
//! `packages/temper-placer/tests/core/test_loop_extraction_marshal_rust_differential.py`
//! (`_oracle_*` blocks).
//!
//! # Panic policy (R1g)
//!
//! Every `#[pymethods]` entry point is wrapped in [`guard`] (`catch_unwind`);
//! no `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};

fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

fn err_attr(name: &str, e: impl std::fmt::Display) -> PyErr {
    pyo3::exceptions::PyValueError::new_err(format!(".{name}: {e}"))
}

fn optional_string(obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if obj.is_none() {
        Ok(None)
    } else {
        obj.extract::<String>().map(Some).map_err(|e| err_attr("net", e))
    }
}

// ---------------------------------------------------------------------------
// LoopExtractionInput — _netlist_to_dict
// ---------------------------------------------------------------------------

/// One component in the extractor-input wire shape. The `mpn`/`value` come
/// from `attributes` (defaulting to `""`), exactly like the oracle's
/// `attributes.get("MPN", "")` / `attributes.get("value", "")`.
#[derive(Debug, Clone)]
struct InputComponent {
    ref_: String,
    footprint: String,
    mpn: String,
    value: String,
    net_class: String,
    pins: Vec<(String, Option<String>)>, // (pin name, net)
}

/// One net in the extractor-input wire shape: `{name, pins: [[ref, name], ..]}`
/// -- the pre-migration `[ref, name] for ref, name in net.pins` pairs,
/// order preserved.
#[derive(Debug, Clone)]
struct InputNet {
    name: String,
    pins: Vec<(String, String)>,
}

/// The typed netlist marshaler for the loop-extractor bridge input
/// (Phase-A U9). Replaces `_netlist_to_dict`; `to_dict()` reproduces the
/// pre-migration dict bit-for-bit.
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct LoopExtractionInput {
    components: Vec<InputComponent>,
    nets: Vec<InputNet>,
    topology_hints: Option<HashMap<String, String>>,
}

#[pymethods]
impl LoopExtractionInput {
    /// `temper_design_bundle_python.LoopExtractionInput.from_netlist(netlist,
    /// topology_hints=None)` — the typed marshaler for `_netlist_to_dict`.
    #[staticmethod]
    #[pyo3(signature = (netlist, topology_hints=None))]
    fn from_netlist(
        netlist: &Bound<'_, PyAny>,
        topology_hints: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<LoopExtractionInput> {
        guard(|| {
            let mut components = Vec::new();
            for c in netlist.getattr("components")?.try_iter()? {
                let c = c?;
                let ref_ = c.getattr("ref")?.extract::<String>()?;
                let footprint = c.getattr("footprint")?.extract::<String>()?;
                let attributes = c.getattr("attributes")?;
                let mpn = attributes.call_method1("get", ("MPN", ""))?.extract::<String>()?;
                let value = attributes.call_method1("get", ("value", ""))?.extract::<String>()?;
                let net_class = c.getattr("net_class")?.extract::<String>()?;
                let mut pins = Vec::new();
                for p in c.getattr("pins")?.try_iter()? {
                    let p = p?;
                    let name = p.getattr("name")?.extract::<String>()?;
                    let net = optional_string(&p.getattr("net")?)?;
                    pins.push((name, net));
                }
                components.push(InputComponent {
                    ref_,
                    footprint,
                    mpn,
                    value,
                    net_class,
                    pins,
                });
            }

            let mut nets = Vec::new();
            for n in netlist.getattr("nets")?.try_iter()? {
                let n = n?;
                let name = n.getattr("name")?.extract::<String>()?;
                let mut wire_pins = Vec::new();
                for pin in n.getattr("pins")?.try_iter()? {
                    let pin = pin?;
                    let ref_ = pin.get_item(0)?.extract::<String>()?;
                    let pin_name = pin.get_item(1)?.extract::<String>()?;
                    wire_pins.push((ref_, pin_name));
                }
                nets.push(InputNet { name, pins: wire_pins });
            }

            // `if topology_hints:` truthiness on the shim side: `None`, `{}`,
            // `""` (and any non-dict) must NOT add a `topology_hints` key --
            // the pre-migration shim only added it for a truthy dict.
            let hints = match topology_hints {
                None => None,
                Some(h) if h.is_none() => None,
                Some(h) => match h.extract::<HashMap<String, String>>() {
                    Ok(map) if !map.is_empty() => Some(map),
                    _ => None,
                },
            };

            Ok(LoopExtractionInput {
                components,
                nets,
                topology_hints: hints,
            })
        })
    }

    /// The pre-migration dict, bit-for-bit (`components` then `nets`, then
    /// a trailing `topology_hints` key only when hints were passed).
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| {
            let d = PyDict::new(py);

            let comps = PyList::empty(py);
            for c in &self.components {
                let cd = PyDict::new(py);
                cd.set_item("ref", &c.ref_)?;
                cd.set_item("footprint", &c.footprint)?;
                cd.set_item("mpn", &c.mpn)?;
                cd.set_item("value", &c.value)?;
                cd.set_item("net_class", &c.net_class)?;
                let pins = PyList::empty(py);
                for (name, net) in &c.pins {
                    let pd = PyDict::new(py);
                    pd.set_item("name", name)?;
                    match net {
                        Some(n) => pd.set_item("net", n)?,
                        None => pd.set_item("net", py.None())?,
                    }
                    pins.append(pd)?;
                }
                cd.set_item("pins", pins)?;
                comps.append(cd)?;
            }
            d.set_item("components", comps)?;

            let nets = PyList::empty(py);
            for n in &self.nets {
                let nd = PyDict::new(py);
                nd.set_item("name", &n.name)?;
                let pins = PyList::empty(py);
                for (ref_, name) in &n.pins {
                    let p = PyList::empty(py);
                    p.append(ref_)?;
                    p.append(name)?;
                    pins.append(p)?;
                }
                nd.set_item("pins", pins)?;
                nets.append(nd)?;
            }
            d.set_item("nets", nets)?;

            if let Some(hints) = &self.topology_hints {
                let hd = PyDict::new(py);
                for (k, v) in hints {
                    hd.set_item(k, v)?;
                }
                d.set_item("topology_hints", hd)?;
            }

            Ok(d.unbind())
        })
    }

    /// CPython `json.dumps(to_dict())` — byte-identical to the
    /// pre-migration `json.dumps(netlist_dict)` (CPython produces the
    /// bytes; nothing is re-implemented Rust-side).
    fn to_json(&self, py: Python<'_>) -> PyResult<String> {
        guard(|| {
            let d = self.to_dict(py)?;
            let json_mod = PyModule::import(py, "json")?;
            json_mod
                .getattr("dumps")?
                .call1((d,))?
                .extract::<String>()
        })
    }
}

// ---------------------------------------------------------------------------
// LoopExtractionOutput — _dict_to_loop_collection's typed wire parse
// ---------------------------------------------------------------------------

/// One extracted loop in the bridge's output wire shape: the five fields
/// the Rust kernel computes (`name`, `loop_type`, `components`, `nets`,
/// `max_area_mm2`). The priority/events/return-path reconstruction onto the
/// Python-dataclass loops stays in the shim (see the module docstring).
#[pyclass(module = "temper_design_bundle_python", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct ExtractedLoopWire {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub loop_type: String,
    #[pyo3(get)]
    pub components: Vec<String>,
    #[pyo3(get)]
    pub nets: Vec<String>,
    #[pyo3(get)]
    pub max_area_mm2: f64,
}

#[pymethods]
impl ExtractedLoopWire {
    #[new]
    #[pyo3(signature = (name, loop_type, components=None, nets=None, max_area_mm2=100.0))]
    fn new(
        name: String,
        loop_type: String,
        components: Option<Vec<String>>,
        nets: Option<Vec<String>>,
        max_area_mm2: f64,
    ) -> Self {
        Self {
            name,
            loop_type,
            components: components.unwrap_or_default(),
            nets: nets.unwrap_or_default(),
            max_area_mm2,
        }
    }
}

/// The typed bridge-output wire (Phase-A U9). Replaces the shim's raw
/// `data.get("loops", [])` dict traversal with a total typed parse carrying
/// the documented defaults.
#[pyclass(module = "temper_design_bundle_python", skip_from_py_object)]
#[derive(Debug)]
pub struct LoopExtractionOutput {
    #[pyo3(get)]
    pub ok: bool,
    #[pyo3(get)]
    pub error: Option<String>,
    loops: Vec<Py<ExtractedLoopWire>>,
}

#[pymethods]
impl LoopExtractionOutput {
    /// Direct construction from the typed fields (used by tests and PBT
    /// vacuity mutants; production builds via `from_dict`/`from_json`).
    #[new]
    #[pyo3(signature = (ok=false, error=None, loops=None))]
    fn new(ok: bool, error: Option<String>, loops: Option<Vec<Py<ExtractedLoopWire>>>) -> Self {
        Self {
            ok,
            error,
            loops: loops.unwrap_or_default(),
        }
    }

    #[staticmethod]
    fn from_dict(data: &Bound<'_, PyDict>) -> PyResult<LoopExtractionOutput> {
        guard(|| {
            let py = data.py();
            let ok = match data.get_item("ok")? {
                Some(v) if v.is_none() => false,
                Some(v) => v.extract::<bool>()?,
                None => false,
            };
            let error = match data.get_item("error")? {
                Some(v) if !v.is_none() => Some(v.extract::<String>()?),
                _ => None,
            };
            let mut loops = Vec::new();
            if let Some(raw) = data.get_item("loops")? {
                for item in raw.try_iter()? {
                    let item = item?;
                    let d = item.cast::<PyDict>()?;
                    // `loop_dict["name"]` -- the oracle raises KeyError on a
                    // missing name (the wire always carries it).
                    let name = d
                        .get_item("name")?
                        .ok_or_else(|| PyKeyError::new_err("'name'"))?
                        .extract::<String>()?;
                    let loop_type = match d.get_item("loop_type")? {
                        Some(v) => v.extract::<String>()?,
                        None => "unknown".to_string(),
                    };
                    let components = match d.get_item("components")? {
                        Some(v) => v.extract::<Vec<String>>()?,
                        None => Vec::new(),
                    };
                    let nets = match d.get_item("nets")? {
                        Some(v) => v.extract::<Vec<String>>()?,
                        None => Vec::new(),
                    };
                    let max_area_mm2 = match d.get_item("max_area_mm2")? {
                        Some(v) => v.extract::<f64>()?,
                        None => 500.0,
                    };
                    let wire = ExtractedLoopWire {
                        name,
                        loop_type,
                        components,
                        nets,
                        max_area_mm2,
                    };
                    loops.push(Py::new(py, wire)?);
                }
            }
            Ok(LoopExtractionOutput { ok, error, loops })
        })
    }

    /// `json.loads(json_str)` then the `from_dict` parse (CPython loads,
    /// nothing re-implemented).
    #[staticmethod]
    fn from_json(py: Python<'_>, json_str: &str) -> PyResult<LoopExtractionOutput> {
        guard(|| {
            let json_mod = PyModule::import(py, "json")?;
            let data = json_mod.getattr("loads")?.call1((json_str,))?;
            Self::from_dict(data.cast::<PyDict>()?)
        })
    }

    /// The typed per-loop wire list (a new Python list per call).
    #[getter]
    fn loops(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        Ok(PyList::new(py, self.loops.iter().map(|l| l.clone_ref(py)))?.unbind())
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LoopExtractionInput>()?;
    module.add_class::<LoopExtractionOutput>()?;
    module.add_class::<ExtractedLoopWire>()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests (pure Rust semantics -- the pyo3 surface is pinned by the
// differential/PBT suites)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn input() -> LoopExtractionInput {
        LoopExtractionInput {
            components: vec![InputComponent {
                ref_: "Q1".into(),
                footprint: "TO-247".into(),
                mpn: "IKW40N120H3".into(),
                value: "1200V 40A".into(),
                net_class: "HighVoltage".into(),
                pins: vec![("GATE".into(), Some("GATE_H".into())), ("E".into(), None)],
            }],
            nets: vec![InputNet {
                name: "SW".into(),
                pins: vec![("Q1".into(), "E".into()), ("Q2".into(), "C".into())],
            }],
            topology_hints: Some(HashMap::from([("topology".into(), "half_bridge".into())])),
        }
    }

    #[test]
    fn wire_loop_new_defaults() {
        let w = ExtractedLoopWire::new(
            "auto_x".into(),
            "commutation".into(),
            None,
            None,
            100.0,
        );
        assert_eq!(w.name, "auto_x");
        assert_eq!(w.loop_type, "commutation");
        assert!(w.components.is_empty());
        assert!(w.nets.is_empty());
    }

    #[test]
    fn wire_loop_holds_fields() {
        let w = ExtractedLoopWire {
            name: "auto_x".into(),
            loop_type: "commutation".into(),
            components: vec!["Q1".into(), "Q2".into()],
            nets: vec!["SW".into()],
            max_area_mm2: 500.0,
        };
        assert_eq!(w.components.len(), 2);
        assert_eq!(w.nets.len(), 1);
        assert_eq!(w.max_area_mm2, 500.0);
    }

    #[test]
    fn input_holds_components_nets_hints() {
        let i = input();
        assert_eq!(i.components.len(), 1);
        assert_eq!(i.components[0].pins.len(), 2);
        assert_eq!(i.components[0].pins[1].1, None);
        assert_eq!(i.nets[0].pins[0], ("Q1".into(), "E".into()));
        assert!(i.topology_hints.as_ref().is_some());
    }
}
