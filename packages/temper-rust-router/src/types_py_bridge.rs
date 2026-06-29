// Python → Rust bridge for constraint model data.
use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use crate::types::{
    BundleClass, InternalBundleManifest, InternalConstraint, InternalConstraintModel,
    InternalVariable,
};

pub fn model_from_python(
    _net_ids: Vec<String>,
    variables: Vec<PyObject>,
    constraints: Vec<PyObject>,
) -> PyResult<InternalConstraintModel> {
    Python::with_gil(|py| {
        let mut vars = Vec::new();
        for v in &variables {
            let obj = v.bind(py);
            let name: String = obj.getattr("name")?.extract()?;
            let has_net1 = obj.getattr("net1_idx").is_ok();
            let has_net_idx = obj.getattr("net_idx").is_ok();
            if has_net1 {
                vars.push(InternalVariable::Ordering {
                    name,
                    net1_idx: obj.getattr("net1_idx")?.extract()?,
                    net2_idx: obj.getattr("net2_idx")?.extract()?,
                    channel_id: obj.getattr("channel_id")?.extract()?,
                });
            } else if obj.getattr("segment_id").is_ok() && has_net_idx {
                vars.push(InternalVariable::NetLayer {
                    name,
                    net_idx: obj.getattr("net_idx")?.extract()?,
                    segment_id: obj.getattr("segment_id")?.extract()?,
                });
            } else if obj.getattr("location_id").is_ok() && has_net_idx {
                vars.push(InternalVariable::Via {
                    name,
                    net_idx: obj.getattr("net_idx")?.extract()?,
                    location_id: obj.getattr("location_id")?.extract()?,
                });
            } else if has_net_idx {
                vars.push(InternalVariable::NetChannel {
                    name,
                    net_idx: obj.getattr("net_idx")?.extract()?,
                    channel_id: obj.getattr("channel_id")?.extract()?,
                });
            }
        }

        let mut cons = Vec::new();
        for c in &constraints {
            let obj = c.bind(py);
            if obj.getattr("capacity").is_ok() {
                let channel_id: String = obj.getattr("channel_id")?.extract()?;
                let capacity: f64 = obj.getattr("capacity")?.extract()?;
                let slack_factor: f64 = obj.getattr("slack_factor")?.extract()?;
                let mut terms = Vec::new();
                if let Ok(terms_bound) = obj.getattr("terms") {
                    let terms_bound = terms_bound;  // Bound<'py, PyAny>
                    if let Ok(terms_list) = terms_bound.downcast::<PyList>() {
                        for i in 0..terms_list.len() {
                            let item = terms_list.get_item(i)?;
                            let tup = item.downcast::<PyTuple>()?;
                            let var_any = tup.get_item(0)?;
                            let vname: String = var_any.getattr("name")?.extract()?;
                            let width: f64 = tup.get_item(1)?.extract()?;
                            terms.push((vname, width));
                        }
                    }
                }
                cons.push(InternalConstraint::Capacity { channel_id, capacity, slack_factor, terms });
            } else if obj.getattr("p_var").is_ok() {
                let channel_id: String = obj.getattr("channel_id")?.extract()?;
                let p_bound = obj.getattr("p_var")?;
                let n_bound = obj.getattr("n_var")?;
                let p_var_name: String = p_bound.getattr("name")?.extract()?;
                let n_var_name: String = n_bound.getattr("name")?.extract()?;
                cons.push(InternalConstraint::DiffPair { channel_id, p_var_name, n_var_name });
            } else if obj.getattr("allowed").is_ok() {
                let net_idx: usize = obj.getattr("net_idx")?.extract()?;
                let channel_id: String = obj.getattr("channel_id")?.extract()?;
                let allowed: bool = obj.getattr("allowed")?.extract()?;
                cons.push(InternalConstraint::LayerRestriction {
                    var_name: format!("uses_N{}_{}", net_idx, channel_id),
                    allowed,
                });
            } else if obj.getattr("group_a_indices").is_ok() {
                let group_a: Vec<usize> = obj.getattr("group_a_indices")?.extract()?;
                let group_b: Vec<usize> = obj.getattr("group_b_indices")?.extract()?;
                let min_slots: usize = obj.getattr("min_slots")?.extract()?;
                let channel_id: String = obj.getattr("channel_id")?.extract()?;
                cons.push(InternalConstraint::ChannelSeparation {
                    group_a,
                    group_b,
                    min_slots,
                    channel_id,
                });
            }
        }
        Ok(InternalConstraintModel { variables: vars, constraints: cons })
    })
}

/// Bridge Python BundleManifest dict to Rust InternalBundleManifest.
pub fn bridge_bundle_manifest(
    py_dict: &Bound<'_, PyDict>,
) -> PyResult<InternalBundleManifest> {
    let binding = py_dict
        .get_item("bundles")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("missing 'bundles'"))?;
    let bundles_list: &Bound<'_, PyList> = binding.downcast()?;

    let mut bundles = Vec::new();
    for item in bundles_list.iter() {
        let d: &Bound<'_, PyDict> = item.downcast()?;
        let bundle_id: usize = d.get_item("bundle_id")?.unwrap().extract()?;
        let net_indices: Vec<usize> = d.get_item("net_indices")?.unwrap().extract()?;
        let constraint_types: Vec<String> = d
            .get_item("constraint_types")?
            .unwrap()
            .extract::<Vec<String>>()?;
        let is_diff_pair: bool = d.get_item("is_diff_pair")?.unwrap().extract()?;

        bundles.push(BundleClass {
            bundle_id,
            net_indices,
            constraint_types,
            is_diff_pair,
        });
    }

    let bfn_binding = py_dict
        .get_item("bundle_id_for_net")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("missing 'bundle_id_for_net'"))?;
    let bfn: &Bound<'_, PyDict> = bfn_binding.downcast()?;
    let mut bundle_id_for_net = HashMap::new();
    for (key, val) in bfn.iter() {
        let net_idx: usize = key.extract()?;
        let bundle_id: usize = val.extract()?;
        bundle_id_for_net.insert(net_idx, bundle_id);
    }

    let unbundled_binding = py_dict
        .get_item("unbundled_net_indices")?
        .unwrap();
    let unbundled: Vec<usize> = unbundled_binding.extract()?;

    Ok(InternalBundleManifest {
        bundles,
        bundle_id_for_net,
        unbundled_net_indices: unbundled,
    })
}
