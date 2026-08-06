//! Wave-4 Phase B: `router_v6/routing_demand.py`, part of the congestion &
//! placement-feedback cluster (cluster E).
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_congestion_py_oracle.py`'s
//! `estimate_routing_demand` and `RoutingDemand.routing_complexity`.
//!
//! # Why the regex classification is delegated to Python
//!
//! The oracle classifies each routable net by running two `re.search` calls
//! against its upper-cased name (`(?:^|_)(?:GND|VCC|VDD|VSS)(?:$|[\d_])` and
//! `^[+-]`). `re.search`'s matching semantics are CPython's `re` engine's,
//! and re-deriving them with hand-written Rust string scanning would risk
//! disagreeing on some boundary case the corpus does not happen to cover.
//! `pyo3` already gives us `re` for free (no new crate dependency), so the
//! match itself is delegated the same way `congestion.rs` delegates
//! elementwise array semantics to `numpy` rather than re-deriving them.

use pyo3::prelude::*;
use pyo3::types::PyAnyMethods;

use crate::congestion::cpython_min2;

/// `(total_nets, routable_nets, total_pins, signal_nets, power_nets,
/// diff_pair_nets, avg_pins_per_net, max_pins_per_net, routing_complexity)`
/// -- the 9-tuple the differential projects `RoutingDemand` to.
type RoutingDemandRow = (i64, i64, i64, i64, i64, i64, f64, i64, f64);

/// `RoutingDemand.routing_complexity`.
///
/// `min(1.0, (avg_pins_per_net / 10.0) * (routable_nets / 100.0))` is
/// CPython's two-argument `min(1.0, x)`: `result = 1.0; if x < result: result
/// = x`. That is exactly [`cpython_min2`]`(1.0, x)` — for a NaN `x`, `x <
/// 1.0` is false, so the `1.0` sticks (the corpus's `avg=NaN` case). Negative
/// `x` is NOT clamped from below: only the upper bound at `1.0` is enforced.
#[pyfunction]
pub fn routing_demand_complexity_py(avg_pins_per_net: f64, routable_nets: i64) -> f64 {
    if routable_nets == 0 {
        return 0.0;
    }
    let value = (avg_pins_per_net / 10.0) * (routable_nets as f64 / 100.0);
    cpython_min2(1.0, value)
}

/// `estimate_routing_demand`, projected as the differential signs it: the
/// 9-tuple `(total_nets, routable_nets, total_pins, signal_nets, power_nets,
/// diff_pair_nets, avg_pins_per_net, max_pins_per_net, routing_complexity)`.
///
/// `components` is `[(ref, [(pin_number, net), ...]), ...]`; `net_names` is
/// the flat net-name list `build_parsed_pcb` uses to build either a `dict`
/// (`as_dict=True`) or a `list` (`as_dict=False`) of nets.
///
/// The `as_dict` flag is not a convenience switch on the Rust side either:
/// `pcb.nets` is a `dict` comprehension over `net_names` when `as_dict` is
/// set, and a **dict comprehension collapses duplicate keys**, keeping only
/// the first position and the last value. `total_nets = len(pcb.nets)` and
/// the net-by-net iteration both read through however many (deduplicated or
/// not) entries that produced — so a `net_names` list with a repeated name
/// yields a *smaller* `total_nets` and one fewer routable-net pass in dict
/// mode than in list mode, for byte-identical input otherwise.
#[pyfunction]
#[pyo3(signature = (components, net_names, as_dict))]
pub fn routing_demand_estimate_py(
    py: Python<'_>,
    components: Vec<(String, Vec<(String, String)>)>,
    net_names: Vec<String>,
    as_dict: bool,
) -> PyResult<RoutingDemandRow> {
    let total_pins: i64 = components.iter().map(|(_, pins)| pins.len() as i64).sum();

    // `pcb.nets` as either a `dict` (dedup, first-seen order kept) or a
    // `list` (duplicates preserved) of the same names, exactly mirroring
    // `build_parsed_pcb`.
    let net_items: Vec<String> = if as_dict {
        let mut seen = std::collections::HashSet::new();
        let mut order = Vec::new();
        for n in &net_names {
            if seen.insert(n.clone()) {
                order.push(n.clone());
            }
        }
        order
    } else {
        net_names.clone()
    };
    let total_nets = net_items.len() as i64;

    let re_mod = py.import("re")?;
    let power_pattern = r"(?:^|_)(?:GND|VCC|VDD|VSS)(?:$|[\d_])";
    let sign_pattern = r"^[+-]";

    let mut routable_nets: i64 = 0;
    let mut pin_counts: Vec<i64> = Vec::new();
    let mut signal_nets: i64 = 0;
    let mut power_nets: i64 = 0;
    let mut diff_pair_nets: i64 = 0;

    for net_name in &net_items {
        let pin_count: i64 = components
            .iter()
            .flat_map(|(_, pins)| pins.iter())
            .filter(|(_, net)| net == net_name)
            .count() as i64;
        let net_name: &str = net_name.as_str();

        if pin_count <= 1 {
            continue;
        }
        routable_nets += 1;
        pin_counts.push(pin_count);

        let net_upper = net_name.to_uppercase();
        let power_hit = re_mod.call_method1("search", (power_pattern, net_upper.as_str()))?;
        let sign_hit = re_mod.call_method1("search", (sign_pattern, net_upper.as_str()))?;
        if !power_hit.is_none() || !sign_hit.is_none() {
            power_nets += 1;
        } else if ["_P", "_N", "DP", "DN"].iter().any(|x| net_upper.contains(*x)) {
            diff_pair_nets += 1;
        } else {
            signal_nets += 1;
        }
    }

    let (avg_pins_per_net, max_pins_per_net) = if pin_counts.is_empty() {
        (0.0, 0i64)
    } else {
        let sum: i64 = pin_counts.iter().sum();
        let avg = sum as f64 / pin_counts.len() as f64;
        let max = pin_counts.iter().copied().max().unwrap_or(0);
        (avg, max)
    };

    let routing_complexity = routing_demand_complexity_py(avg_pins_per_net, routable_nets);

    Ok((
        total_nets,
        routable_nets,
        total_pins,
        signal_nets,
        power_nets,
        diff_pair_nets,
        avg_pins_per_net,
        max_pins_per_net,
        routing_complexity,
    ))
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(routing_demand_estimate_py, m)?)?;
    m.add_function(wrap_pyfunction!(routing_demand_complexity_py, m)?)?;
    Ok(())
}
