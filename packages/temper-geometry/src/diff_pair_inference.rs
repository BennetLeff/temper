// Wave 4: `temper_placer/router_v6/diff_pair_inference.py` — Stage 0.2
// differential-pair inference from net naming conventions.  The `DiffPair`
// dataclass (with its `p_net != n_net` validation) stays in Python; the
// whole three-pass suffix-matching algorithm crosses this boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_spatial_drc_cluster_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Contract
// ---------------------------------------------------------------------------
// * `net_map = {name.upper(): name for name in net_names}` — last duplicate
//   wins (HashMap insert-overwrite), and lookups by uppercased key return
//   the original-case name.
// * Three passes run in order (+/- then _DP/DP then _P/P); every pass
//   skips nets already `matched`.  The output order follows the reference
//   exactly (input list order per pass).
// * `base_name` is the UPPERCASED base (the reference slices the uppercased
//   net name), while `p_net`/`n_net` are the original-case names.
// * Byte slicing: `upper[..len-1]` etc.  Rust `String::len()` is bytes;
//   Python `len()` is characters.  They coincide for ASCII net names, which
//   is the pinned contract (differential inputs are ASCII).

use std::collections::{HashMap, HashSet};

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// `infer_differential_pairs`: returns `(base_name, p_net, n_net)` triples
/// in the reference's discovery order.
pub fn infer_differential_pairs(net_names: &[String]) -> Vec<(String, String, String)> {
    let mut net_map: HashMap<String, &str> = HashMap::with_capacity(net_names.len());
    for name in net_names {
        net_map.insert(name.to_ascii_uppercase(), name.as_str());
    }

    let mut matched: HashSet<String> = HashSet::new();
    let mut pairs: Vec<(String, String, String)> = Vec::new();

    // Pattern 1: +/- suffix.
    for name in net_names {
        let upper = name.to_ascii_uppercase();
        if matched.contains(&upper) {
            continue;
        }
        if upper.ends_with('+') {
            let base = upper[..upper.len() - 1].to_string();
            let neg_candidate = format!("{base}-");
            if net_map.contains_key(&neg_candidate) {
                let p = net_map[&upper].to_string();
                let n = net_map[&neg_candidate].to_string();
                pairs.push((base, p, n));
                matched.insert(upper);
                matched.insert(neg_candidate);
            }
        }
    }

    // Pattern 2: _DP / DP suffix (before _P/_N to avoid USB_DP matching as
    // USB_D_P).
    for name in net_names {
        let upper = name.to_ascii_uppercase();
        if matched.contains(&upper) {
            continue;
        }
        if upper.ends_with("_DP") {
            let base = upper[..upper.len() - 3].to_string();
            let neg_candidate = format!("{base}_DN");
            if net_map.contains_key(&neg_candidate) {
                let p = net_map[&upper].to_string();
                let n = net_map[&neg_candidate].to_string();
                pairs.push((base, p, n));
                matched.insert(upper);
                matched.insert(neg_candidate);
            }
        } else if upper.ends_with("DP") && !upper.ends_with("_DP") && upper.len() > 2 {
            let base = upper[..upper.len() - 2].to_string();
            let neg_candidate = format!("{base}DN");
            if net_map.contains_key(&neg_candidate) {
                let p = net_map[&upper].to_string();
                let n = net_map[&neg_candidate].to_string();
                pairs.push((base, p, n));
                matched.insert(upper);
                matched.insert(neg_candidate);
            }
        }
    }

    // Pattern 3: _P / _N suffix.
    for name in net_names {
        let upper = name.to_ascii_uppercase();
        if matched.contains(&upper) {
            continue;
        }
        if upper.ends_with("_P") {
            let base = upper[..upper.len() - 2].to_string();
            let neg_candidate = format!("{base}_N");
            if net_map.contains_key(&neg_candidate) {
                let p = net_map[&upper].to_string();
                let n = net_map[&neg_candidate].to_string();
                pairs.push((base, p, n));
                matched.insert(upper);
                matched.insert(neg_candidate);
            }
        } else if upper.ends_with('P') && !upper.ends_with("DP") && upper.len() > 1 {
            let base = upper[..upper.len() - 1].to_string();
            let neg_candidate = format!("{base}N");
            if net_map.contains_key(&neg_candidate) {
                let p = net_map[&upper].to_string();
                let n = net_map[&neg_candidate].to_string();
                pairs.push((base, p, n));
                matched.insert(upper);
                matched.insert(neg_candidate);
            }
        }
    }

    pairs
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn infer_differential_pairs_py(net_names: Vec<String>) -> PyResult<Vec<(String, String, String)>> {
    temper_py_bridge::catch_unwind(|| infer_differential_pairs(&net_names))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(infer_differential_pairs_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn names(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[cfg_attr(test, test)]
    fn plus_minus_suffix() {
        let pairs = infer_differential_pairs(&names(&["USB_D+", "USB_D-", "GND"]));
        assert_eq!(pairs, vec![("USB_D".to_string(), "USB_D+".to_string(), "USB_D-".to_string())]);
    }

    #[cfg_attr(test, test)]
    fn dp_dn_underscore_and_bare() {
        // The reference's `upper[:-3]` on "USB_DP" yields "USB" (the module
        // docstring's 'USB_D' example is stale relative to the code; the
        // differential pins the code).
        let pairs = infer_differential_pairs(&names(&["USB_DP", "USB_DN"]));
        assert_eq!(pairs, vec![("USB".to_string(), "USB_DP".to_string(), "USB_DN".to_string())]);
        let pairs2 = infer_differential_pairs(&names(&["USBDP", "USBDN"]));
        assert_eq!(pairs2, vec![("USB".to_string(), "USBDP".to_string(), "USBDN".to_string())]);
    }

    #[cfg_attr(test, test)]
    fn p_n_suffix() {
        let pairs = infer_differential_pairs(&names(&["CLK_P", "CLK_N"]));
        assert_eq!(pairs, vec![("CLK".to_string(), "CLK_P".to_string(), "CLK_N".to_string())]);
        let pairs2 = infer_differential_pairs(&names(&["TX+", "TX-", "GND"]));
        assert_eq!(pairs2, vec![("TX".to_string(), "TX+".to_string(), "TX-".to_string())]);
    }

    #[cfg_attr(test, test)]
    fn case_insensitive_and_no_pairs() {
        let pairs = infer_differential_pairs(&names(&["usb_dp", "USB_DN"]));
        assert_eq!(pairs.len(), 1);
        assert_eq!(pairs[0].0, "USB");
        assert_eq!(pairs[0].1, "usb_dp");
        assert_eq!(pairs[0].2, "USB_DN");
        assert_eq!(infer_differential_pairs(&names(&["GND", "3V3", "SIG1"])), vec![]);
    }

    #[cfg_attr(test, test)]
    fn no_net_in_two_pairs() {
        // "USB_DP" pairs with "USB_DN" in pattern 2; neither can then pair
        // again in pattern 3.
        let pairs = infer_differential_pairs(&names(&["USB_DP", "USB_DN", "USB_P", "USB_N"]));
        assert_eq!(pairs.len(), 2);
        // both pairs present; membership of the matched set enforced by
        // construction (no duplicated net).
        let all: Vec<String> = pairs.iter().flat_map(|(_, p, n)| vec![p.clone(), n.clone()]).collect();
        let uniq: HashSet<&String> = all.iter().collect();
        assert_eq!(all.len(), uniq.len());
    }

    #[cfg_attr(test, test)]
    fn p_suffix_skips_dp_and_underscore_p() {
        // "DIGP" is pattern-3 bare P; "DIG_P" is pattern-3 _P; both need a
        // matching "-N"-suffixed net.
        let pairs = infer_differential_pairs(&names(&["DIGP", "DIGN"]));
        assert_eq!(pairs, vec![("DIG".to_string(), "DIGP".to_string(), "DIGN".to_string())]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("diff_pair_inference::tests::plus_minus_suffix", plus_minus_suffix),
        ("diff_pair_inference::tests::dp_dn_underscore_and_bare", dp_dn_underscore_and_bare),
        ("diff_pair_inference::tests::p_n_suffix", p_n_suffix),
        ("diff_pair_inference::tests::case_insensitive_and_no_pairs", case_insensitive_and_no_pairs),
        ("diff_pair_inference::tests::no_net_in_two_pairs", no_net_in_two_pairs),
        ("diff_pair_inference::tests::p_suffix_skips_dp_and_underscore_p", p_suffix_skips_dp_and_underscore_p),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
