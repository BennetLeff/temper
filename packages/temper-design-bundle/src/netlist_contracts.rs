//! Wave 4 Phase 3: netlist contract pyclasses — `Pin`, `Component`, `Net`,
//! `Netlist` — ported from `temper_placer/core/netlist.py`, pinned at the
//! pre-migration commit in `tests/core/_netlist_py_oracle.py`.
//!
//! Division of labor (R10/KTD6/KTD7): `get_bounds_array`/`get_fixed_mask`
//! (numpy float32/bool), `build_adjacency_matrix`, `compute_eigenvector_
//! centrality` (the `np.linalg.eigh` kernel — never gated), and
//! `find_isomorphic_groups` (hashlib-based non-data helper) stay in the
//! Python delegation shim.
//!
//! The Netlist lookup caches (`_component_index`, `_net_index`,
//! `_component_nets`) are `repr=False` dataclass fields — the repr omits
//! them, and the pyclass keeps them as private fields rebuilt by
//! `build_indices`.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

fn py_str_repr(s: &str) -> String {
    format!("'{s}'")
}

fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    let rendered = format!("{v:?}");
    let Some(e_pos) = rendered.find(['e', 'E']) else {
        return rendered;
    };
    let (mantissa, exponent) = rendered.split_at(e_pos);
    let exponent = &exponent[1..];
    let (sign, digits) = match exponent.strip_prefix('-') {
        Some(rest) => ('-', rest),
        None => ('+', exponent),
    };
    let padded = if digits.len() < 2 {
        format!("0{digits}")
    } else {
        digits.to_string()
    };
    format!("{mantissa}e{sign}{padded}")
}

fn opt_str_field(v: Option<&str>) -> String {
    match v {
        Some(s) => py_str_repr(s),
        None => "None".to_string(),
    }
}

fn bool_str(v: bool) -> String {
    if v {
        "True".to_string()
    } else {
        "False".to_string()
    }
}

#[pyclass]
pub struct Pin {
    #[pyo3(get, set)]
    name: String,
    #[pyo3(get, set)]
    number: String,
    #[pyo3(get, set)]
    position: Py<PyAny>,
    #[pyo3(get, set)]
    net: Option<String>,
    #[pyo3(get, set)]
    width: f64,
    #[pyo3(get, set)]
    height: f64,
    #[pyo3(get, set)]
    shape: String,
    #[pyo3(get, set)]
    layer: String,
    /// Dataclass semantics: the parser passes kiutils objects through
    /// (e.g. a `DrillDefinition` for THT pads); the oracle stores whatever
    /// it receives. Py<PyAny> keeps that pass-through.
    #[pyo3(get, set)]
    drill: Py<PyAny>,
    #[pyo3(get, set)]
    is_pth: bool,
    #[pyo3(get, set)]
    roundrect_ratio: f64,
    #[pyo3(get, set)]
    pad_rotation_deg: f64,
}

#[pymethods]
impl Pin {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (name, number, position, net=None, width=1.0, height=1.0, shape="rect".to_string(), layer="F.Cu".to_string(), drill=None, is_pth=false, roundrect_ratio=0.25, pad_rotation_deg=0.0))]
    fn new(
        py: Python<'_>,
        name: String,
        number: String,
        position: Bound<'_, PyAny>,
        net: Option<String>,
        width: f64,
        height: f64,
        shape: String,
        layer: String,
        drill: Option<Bound<'_, PyAny>>,
        is_pth: bool,
        roundrect_ratio: f64,
        pad_rotation_deg: f64,
    ) -> Self {
        let drill = match drill {
            Some(d) => d.unbind(),
            None => {
                let zero: Bound<'_, pyo3::types::PyFloat> = 0.0.into_pyobject(py).unwrap();
                zero.into_any().unbind()
            }
        };
        Self {
            name,
            number,
            position: position.unbind(),
            net,
            width,
            height,
            shape,
            layer,
            drill,
            is_pth,
            roundrect_ratio,
            pad_rotation_deg,
        }
    }

    #[getter]
    fn mask_expansion(&self) -> f64 {
        if self.is_pth {
            0.15
        } else {
            0.1
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Pin(name={}, number={}, position={}, net={}, width={}, height={}, shape={}, layer={}, drill={}, is_pth={}, roundrect_ratio={}, pad_rotation_deg={})",
            py_str_repr(&self.name),
            py_str_repr(&self.number),
            self.position.bind(py).repr()?,
            opt_str_field(self.net.as_deref()),
            py_float_str(self.width),
            py_float_str(self.height),
            py_str_repr(&self.shape),
            py_str_repr(&self.layer),
            self.drill.bind(py).repr()?,
            bool_str(self.is_pth),
            py_float_str(self.roundrect_ratio),
            py_float_str(self.pad_rotation_deg),
        ))
    }
}

/// The extension's flat namespace already holds board's `Component`
/// (different class, same name); pyo3 cannot register two `Component`
/// classes, so this one is exposed as `NetlistComponent` and the Python
/// shim re-exports it as `temper_placer.core.netlist.Component`.
#[pyclass(name = "NetlistComponent")]
pub struct Component {
    /// The dataclass field is `ref` (a Python keyword); exposed as `.ref`.
    #[pyo3(get, set, name = "ref")]
    ref_: String,
    #[pyo3(get, set)]
    footprint: String,
    #[pyo3(get, set)]
    bounds: Py<PyAny>,
    #[pyo3(get, set)]
    pins: Py<PyAny>,
    #[pyo3(get, set)]
    net_class: String,
    #[pyo3(get, set)]
    zone: Option<String>,
    #[pyo3(get, set)]
    fixed: bool,
    #[pyo3(get, set)]
    initial_position: Py<PyAny>,
    #[pyo3(get, set)]
    initial_rotation: Option<isize>,
    #[pyo3(get, set)]
    initial_side: Option<isize>,
    #[pyo3(get, set)]
    attributes: Py<PyAny>,
    #[pyo3(get, set)]
    tags: Py<PyAny>,
    #[pyo3(get, set)]
    sheetpath: Option<String>,
}

#[pymethods]
impl Component {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (r#ref, footprint, bounds, pins=None, net_class="Signal".to_string(), zone=None, fixed=false, initial_position=None, initial_rotation=None, initial_side=None, attributes=None, tags=None, sheetpath=None))]
    fn new(
        py: Python<'_>,
        r#ref: String,
        footprint: String,
        bounds: Bound<'_, PyAny>,
        pins: Option<Bound<'_, PyAny>>,
        net_class: String,
        zone: Option<String>,
        fixed: bool,
        initial_position: Option<Bound<'_, PyAny>>,
        initial_rotation: Option<isize>,
        initial_side: Option<isize>,
        attributes: Option<Bound<'_, PyAny>>,
        tags: Option<Bound<'_, PyAny>>,
        sheetpath: Option<String>,
    ) -> Self {
        let pins = match pins {
            Some(p) => p.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let initial_position = match initial_position {
            Some(p) => p.unbind(),
            None => py.None(),
        };
        let attributes = match attributes {
            Some(a) => a.unbind(),
            None => PyDict::new(py).into_any().unbind(),
        };
        let tags = match tags {
            Some(t) => t.unbind(),
            None => py
                .import("builtins")
                .and_then(|b| b.getattr("frozenset"))
                .and_then(|f| f.call0())
                .map(|f| f.unbind())
                .unwrap_or_else(|_| py.None()),
        };
        Self {
            ref_: r#ref,
            footprint,
            bounds: bounds.unbind(),
            pins,
            net_class,
            zone,
            fixed,
            initial_position,
            initial_rotation,
            initial_side,
            attributes,
            tags,
            sheetpath,
        }
    }

    #[getter]
    fn width(&self, py: Python<'_>) -> PyResult<f64> {
        self.bounds.bind(py).get_item(0)?.extract()
    }

    #[getter]
    fn height(&self, py: Python<'_>) -> PyResult<f64> {
        self.bounds.bind(py).get_item(1)?.extract()
    }

    #[pyo3(signature = (name_or_number))]
    fn get_pin(&self, py: Python<'_>, name_or_number: &str) -> PyResult<Py<PyAny>> {
        for pin in self.pins.bind(py).try_iter()? {
            let pin = pin?;
            let name: String = pin.getattr("name")?.extract()?;
            let number: String = pin.getattr("number")?.extract()?;
            if name == name_or_number || number == name_or_number {
                return Ok(pin.unbind());
            }
        }
        Ok(py.None())
    }

    fn get_pins_for_net(&self, py: Python<'_>, net_name: &str) -> PyResult<Py<PyList>> {
        let out = PyList::empty(py);
        for pin in self.pins.bind(py).try_iter()? {
            let pin = pin?;
            let net: Option<String> = pin.getattr("net")?.extract()?;
            if net.as_deref() == Some(net_name) {
                out.append(pin)?;
            }
        }
        Ok(out.unbind())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Component(ref={}, footprint={}, bounds={}, pins={}, net_class={}, zone={}, fixed={}, initial_position={}, initial_rotation={}, initial_side={}, attributes={}, tags={}, sheetpath={})",
            py_str_repr(&self.ref_),
            py_str_repr(&self.footprint),
            self.bounds.bind(py).repr()?,
            self.pins.bind(py).repr()?,
            py_str_repr(&self.net_class),
            opt_str_field(self.zone.as_deref()),
            bool_str(self.fixed),
            self.initial_position.bind(py).repr()?,
            opt_int_field(self.initial_rotation),
            opt_int_field(self.initial_side),
            self.attributes.bind(py).repr()?,
            self.tags.bind(py).repr()?,
            opt_str_field(self.sheetpath.as_deref()),
        ))
    }
}

fn opt_int_field(v: Option<isize>) -> String {
    match v {
        Some(i) => i.to_string(),
        None => "None".to_string(),
    }
}

#[pyclass]
pub struct Net {
    #[pyo3(get, set)]
    name: String,
    #[pyo3(get, set)]
    pins: Py<PyAny>,
    #[pyo3(get, set)]
    net_class: String,
    #[pyo3(get, set)]
    weight: f64,
    #[pyo3(get, set)]
    max_current: f64,
    #[pyo3(get, set)]
    voltage_class: String,
}

#[pymethods]
impl Net {
    #[new]
    #[pyo3(signature = (name, pins=None, net_class="Signal".to_string(), weight=1.0, max_current=0.0, voltage_class="LV".to_string()))]
    fn new(
        py: Python<'_>,
        name: String,
        pins: Option<Bound<'_, PyAny>>,
        net_class: String,
        weight: f64,
        max_current: f64,
        voltage_class: String,
    ) -> Self {
        let pins = match pins {
            Some(p) => p.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        Self {
            name,
            pins,
            net_class,
            weight,
            max_current,
            voltage_class,
        }
    }

    #[getter]
    fn pin_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.pins.bind(py).len()
    }

    fn get_component_refs(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let refs = py.import("builtins")?.getattr("set")?.call0()?;
        for pin in self.pins.bind(py).try_iter()? {
            let pin = pin?;
            let ref_ = pin.get_item(0)?;
            refs.call_method1("add", (ref_,))?;
        }
        Ok(refs.unbind())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Net(name={}, pins={}, net_class={}, weight={}, max_current={}, voltage_class={})",
            py_str_repr(&self.name),
            self.pins.bind(py).repr()?,
            py_str_repr(&self.net_class),
            py_float_str(self.weight),
            py_float_str(self.max_current),
            py_str_repr(&self.voltage_class),
        ))
    }
}

#[pyclass]
pub struct Netlist {
    #[pyo3(get, set)]
    components: Py<PyAny>,
    #[pyo3(get, set)]
    nets: Py<PyAny>,
    /// Lookup caches (repr=False dataclass fields).
    component_index: Py<PyDict>,
    net_index: Py<PyDict>,
    component_nets: Py<PyDict>,
}

impl Netlist {
    fn rebuild_indices(&mut self, py: Python<'_>) -> PyResult<()> {
        let comp_index = PyDict::new(py);
        for (i, comp) in self.components.bind(py).try_iter()?.enumerate() {
            let comp = comp?;
            let ref_: String = comp.getattr("ref")?.extract()?;
            comp_index.set_item(ref_, i)?;
        }
        let net_index = PyDict::new(py);
        for (i, net) in self.nets.bind(py).try_iter()?.enumerate() {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            net_index.set_item(name, i)?;
        }
        let component_nets = PyDict::new(py);
        for comp in self.components.bind(py).try_iter()? {
            let comp = comp?;
            let ref_: String = comp.getattr("ref")?.extract()?;
            let nets_list = PyList::empty(py);
            component_nets.set_item(ref_, nets_list)?;
        }
        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            let net_name: String = net.getattr("name")?.extract()?;
            for pin in net.getattr("pins")?.try_iter()? {
                let pin = pin?;
                let ref_: String = pin.get_item(0)?.extract()?;
                if let Some(list) = component_nets.get_item(ref_)? {
                    list.call_method1("append", (net_name.clone(),))?;
                }
            }
        }
        self.component_index = comp_index.unbind();
        self.net_index = net_index.unbind();
        self.component_nets = component_nets.unbind();
        Ok(())
    }
}

#[pymethods]
impl Netlist {
    #[new]
    #[pyo3(signature = (components=None, nets=None))]
    fn new(
        py: Python<'_>,
        components: Option<Bound<'_, PyAny>>,
        nets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let components = match components {
            Some(c) => c.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let nets = match nets {
            Some(n) => n.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let mut netlist = Self {
            components,
            nets,
            component_index: PyDict::new(py).unbind(),
            net_index: PyDict::new(py).unbind(),
            component_nets: PyDict::new(py).unbind(),
        };
        netlist.rebuild_indices(py)?;
        Ok(netlist)
    }

    fn build_indices(&mut self, py: Python<'_>) -> PyResult<()> {
        self.rebuild_indices(py)
    }

    fn get_component_index(&self, py: Python<'_>, ref_: &str) -> PyResult<usize> {
        let idx = self
            .component_index
            .bind(py)
            .get_item(ref_)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(ref_.to_owned()))?;
        idx.extract()
    }

    fn get_component(&self, py: Python<'_>, ref_: &str) -> PyResult<Py<PyAny>> {
        let idx: usize = self.get_component_index(py, ref_)?;
        Ok(self.components.bind(py).get_item(idx)?.unbind())
    }

    fn get_net(&self, py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
        let idx = self
            .net_index
            .bind(py)
            .get_item(name)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(name.to_owned()))?;
        let idx: usize = idx.extract()?;
        Ok(self.nets.bind(py).get_item(idx)?.unbind())
    }

    fn get_component_nets(&self, py: Python<'_>, ref_: &str) -> PyResult<Py<PyAny>> {
        match self.component_nets.bind(py).get_item(ref_)? {
            Some(list) => Ok(list.unbind()),
            None => Ok(PyList::empty(py).into_any().unbind()),
        }
    }

    fn get_net_pins(&self, py: Python<'_>, net_name: &str) -> PyResult<Py<PyAny>> {
        let net = self.get_net(py, net_name)?;
        Ok(net.bind(py).getattr("pins")?.unbind())
    }

    #[getter]
    fn n_components(&self, py: Python<'_>) -> PyResult<usize> {
        self.components.bind(py).len()
    }

    #[getter]
    fn n_nets(&self, py: Python<'_>) -> PyResult<usize> {
        self.nets.bind(py).len()
    }

    #[pyo3(signature = (mapping))]
    fn apply_net_class_mapping(&self, py: Python<'_>, mapping: Bound<'_, PyAny>) -> PyResult<usize> {
        let mut updated = 0usize;
        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            if mapping.contains(name.clone())? {
                let new_class: String = mapping.get_item(name.clone())?.extract()?;
                let current: String = net.getattr("net_class")?.extract()?;
                if current != new_class {
                    net.setattr("net_class", new_class)?;
                    updated += 1;
                }
            }        }
        Ok(updated)
    }

    fn validate(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        let errors = PyList::empty(py);

        let mut refs: Vec<String> = Vec::new();
        for comp in self.components.bind(py).try_iter()? {
            let comp = comp?;
            refs.push(comp.getattr("ref")?.extract()?);
        }
        let mut seen = std::collections::HashSet::new();
        let mut dupes: Vec<String> = Vec::new();
        for r in &refs {
            if !seen.insert(r.clone()) && !dupes.contains(r) {
                dupes.push(r.clone());
            }
        }
        if !dupes.is_empty() {
            let set_repr = py
                .import("builtins")?
                .getattr("set")?
                .call1((dupes,))?
                .repr()?;
            errors.append(format!("Duplicate component refs: {set_repr}"))?;
        }

        let mut names: Vec<String> = Vec::new();
        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            names.push(net.getattr("name")?.extract()?);
        }
        let mut seen_names = std::collections::HashSet::new();
        let mut dup_names: Vec<String> = Vec::new();
        for n in &names {
            if !seen_names.insert(n.clone()) && !dup_names.contains(n) {
                dup_names.push(n.clone());
            }
        }
        if !dup_names.is_empty() {
            let set_repr = py
                .import("builtins")?
                .getattr("set")?
                .call1((dup_names,))?
                .repr()?;
            errors.append(format!("Duplicate net names: {set_repr}"))?;
        }

        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            let net_name: String = net.getattr("name")?.extract()?;
            for pin in net.getattr("pins")?.try_iter()? {
                let pin = pin?;
                let ref_: String = pin.get_item(0)?.extract()?;
                let pin_name: String = pin.get_item(1)?.extract()?;
                let comp = match self.get_component(py, &ref_) {
                    Ok(c) => c,
                    Err(_) => {
                        errors.append(format!(
                            "Net {net_name} references unknown component {ref_}"
                        ))?;
                        continue;
                    }
                };
                let found: bool = comp
                    .bind(py)
                    .call_method1("get_pin", (pin_name.clone(),))?
                    .is_none();
                if found {
                    errors.append(format!(
                        "Net {net_name} references unknown pin {pin_name} on {ref_}"
                    ))?;
                }
            }
        }
        Ok(errors.unbind())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        // repr=False on the caches: the dataclass repr omits them.
        Ok(format!(
            "Netlist(components={}, nets={})",
            self.components.bind(py).repr()?,
            self.nets.bind(py).repr()?,
        ))
    }
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Pin>()?;
    module.add_class::<Component>()?;
    module.add_class::<Net>()?;
    module.add_class::<Netlist>()?;
    Ok(())
}
