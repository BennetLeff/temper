pub mod desugar_tier0;
pub mod desugar_tier1;
pub mod ir_tier0;
pub mod ir_tier1;
pub mod provenance;
pub mod pyo3_bridge;
pub mod type_lattice;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

#[pyfunction]
fn compile_pcl_constraints(
    py: Python<'_>,
    pcl_dicts: &Bound<'_, PyList>,
    net_class_dicts: &Bound<'_, PyList>,
    component_map: &Bound<'_, PyDict>,
    zone_map: &Bound<'_, PyDict>,
    skeletons: &Bound<'_, PyList>,
    channel_widths: &Bound<'_, PyDict>,
    existing_vars: &Bound<'_, PyList>,
    existing_cons: &Bound<'_, PyList>,
    net_names: Vec<String>,
) -> PyResult<PyObject> {
    pyo3_bridge::run_full_pipeline(
        py,
        pcl_dicts,
        net_class_dicts,
        component_map,
        zone_map,
        skeletons,
        channel_widths,
        existing_vars,
        existing_cons,
        net_names,
    )
}

#[pyclass]
struct PyCompiler {
    _lattice: Option<crate::type_lattice::TypeLattice>,
    comp_map: std::collections::HashMap<String, usize>,
    zone_map: std::collections::HashMap<String, crate::ir_tier0::Rect>,
    topology: Option<crate::ir_tier1::ChannelTopology>,
    last_model: Option<crate::ir_tier1::ResolvedConstraintModel>,
    prov: crate::provenance::ProvenanceMap,
}

#[pymethods]
impl PyCompiler {
    #[new]
    fn new(
        _py: Python<'_>,
        net_class_dicts: &Bound<'_, PyList>,
        component_map: &Bound<'_, PyDict>,
        zone_map: &Bound<'_, PyDict>,
        skeletons: &Bound<'_, PyList>,
        channel_widths: &Bound<'_, PyDict>,
    ) -> PyResult<Self> {
        let metadata =
            crate::pyo3_bridge::build_net_class_metadata_from_py(net_class_dicts)?;
        let lattice = crate::type_lattice::TypeLattice::new(metadata);
        let comp_map =
            crate::pyo3_bridge::build_component_map_from_py_dict(component_map)?;
        let zone_map_resolved =
            crate::pyo3_bridge::build_zone_map_from_py_dict(zone_map)?;
        let topology =
            crate::pyo3_bridge::build_channel_topology_from_py(skeletons, channel_widths)?;

        let prov = crate::provenance::ProvenanceMap::new();

        Ok(Self {
            _lattice: Some(lattice),
            comp_map,
            zone_map: zone_map_resolved,
            topology: Some(topology),
            last_model: None,
            prov,
        })
    }

    fn compile(
        &mut self,
        py: Python<'_>,
        pcl_dicts: &Bound<'_, PyList>,
        _net_names: Vec<String>,
    ) -> PyResult<PyObject> {
        let pcl_constraints =
            crate::pyo3_bridge::build_pcl_constraints_from_py(pcl_dicts)?;

        let pcl_model = crate::ir_tier0::PclConstraintModel::new(pcl_constraints, vec![]);

        let resolver = crate::pyo3_bridge::HashMapResolver {
            component_map: self.comp_map.clone(),
            zone_map: self.zone_map.clone(),
        };

        let tier1_model = crate::desugar_tier0::compile_tier0_to_tier1(
            &pcl_model,
            &resolver,
            &resolver,
            &mut self.prov,
        )
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Tier 0→1: {e}"))
        })?;

        let conflicts =
            crate::provenance::detect_conflicts(&tier1_model.constraints);

        let tier2_constraints = crate::desugar_tier1::compile_tier1_to_tier2(
            &tier1_model,
            self.topology.as_ref().ok_or_else(|| {
                PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("no topology")
            })?,
            &mut self.prov,
        )
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Tier 1→2: {e}"))
        })?;

        self.last_model = Some(tier1_model);

        let constraint_dicts: Vec<PyObject> = tier2_constraints
            .iter()
            .map(|c| {
                crate::pyo3_bridge::internal_constraint_to_py_dict(py, c)
            })
            .collect::<Result<Vec<_>, _>>()?;

        let conflict_dicts: Vec<PyObject> = conflicts
            .iter()
            .map(|c| {
                let d = PyDict::new(py);
                d.set_item("pcl_constraint_ids", c.pcl_constraint_ids.clone())
                    .unwrap();
                d.set_item("description", &c.description).unwrap();
                d.set_item("tier", format!("{}", c.tier)).unwrap();
                d.clone().into()
            })
            .collect();

        let result = PyDict::new(py);
        result.set_item("constraints", constraint_dicts)?;
        result.set_item("conflicts", conflict_dicts)?;
        result.set_item("num_lowered", tier2_constraints.len())?;
        Ok(result.into())
    }

    fn recompile_delta(
        &mut self,
        _py: Python<'_>,
        _changed_net_indices: Vec<usize>,
    ) -> PyResult<PyObject> {
        Err(PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>(
            "recompile_delta: incremental recompilation not yet implemented",
        ))
    }

    fn reverse_map_unsat_core(
        &self,
        py: Python<'_>,
        unsat_core_indices: Vec<usize>,
    ) -> PyResult<PyObject> {
        let diagnostics =
            crate::provenance::reverse_map_unsat_core(&unsat_core_indices, &self.prov);
        let list = PyList::empty(py);
        for diag in &diagnostics {
            list.append(crate::pyo3_bridge::diagnostic_to_py_dict(py, diag)?)?;
        }
        Ok(list.into())
    }
}

#[pymodule]
fn temper_constraint_compiler(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compile_pcl_constraints, m)?)?;
    m.add_class::<PyCompiler>()?;
    Ok(())
}
