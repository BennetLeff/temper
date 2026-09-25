//! Bounded thermal network for the GBJ2510 bridge package.
//!
//! The package is represented as four diode junction nodes, one case node,
//! and four lead nodes.  This is a deliberately small linear model: package
//! internals and mutual die paths are not inferred from the datasheet.

use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};

pub const REVIEWED_SOURCE_SHA256: &str =
    "c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02";
const AMBIENT_K: f64 = 333.15;
const EXPECTED_POWER_W: f64 = 40.0;
const EDGES: [(usize, usize); 4] = [(1, 0), (2, 0), (3, 1), (3, 2)];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Nodes {
    pub junction_k: [f64; 4],
    pub case_k: f64,
    pub lead_k: [f64; 4],
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Balances {
    pub lead_residual_w: [f64; 4],
    pub junction_residual_w: [f64; 4],
    pub case_residual_w: f64,
    pub sink_w: f64,
}

/// Solve the bounded nine-node package network.
pub fn solve(
    old: [f64; 4],
    outward: [f64; 4],
    g: [f64; 4],
    diode_power_w: [f64; 4],
    weak: bool,
) -> Result<Nodes> {
    solve_at_sink(old, outward, g, diode_power_w, weak, AMBIENT_K)
}

/// Solve with an explicitly supplied case sink temperature in kelvin.
pub fn solve_at_sink(
    old: [f64; 4],
    outward: [f64; 4],
    g: [f64; 4],
    diode_power_w: [f64; 4],
    weak: bool,
    sink_k: f64,
) -> Result<Nodes> {
    if !sink_k.is_finite() || sink_k <= 0.0 {
        bail!("sink temperature must be finite");
    }
    validate_inputs(old, outward, g, diode_power_w)?;
    let link = if weak { 0.05 } else { 0.1 };
    let gjc = if weak { 1.0 / 1.5 } else { 1.0 };
    let gcs = if weak { 1.0 / 0.5 } else { 1.0 / 0.25 };

    let mut a = [[0.0_f64; 9]; 9];
    let mut b = [0.0_f64; 9];
    // Junctions and their case paths.
    for j in 0..4 {
        a[j][j] += 2.0 * link + gjc;
        a[j][4] -= gjc;
        let (u, v) = EDGES[j];
        a[j][5 + u] -= link;
        a[j][5 + v] -= link;
    }
    b[..4].copy_from_slice(&diode_power_w);
    // Case-to-sink path.
    a[4][4] += 4.0 * gjc + gcs;
    a[4][..4].fill(-gjc);
    b[4] = gcs * sink_k;
    // Lead source ports plus their two diode links.  The source conductance
    // is the caller's FEM linear-response g[i], independently of link g.
    for i in 0..4 {
        let row = 5 + i;
        a[row][row] += 2.0 * link + g[i];
        b[row] = outward[i] + g[i] * old[i];
        for (j, &(u, v)) in EDGES.iter().enumerate() {
            if u == i || v == i {
                a[row][j] -= link;
            }
        }
    }
    let x = gaussian_solve(a, b)?;
    let nodes = Nodes {
        junction_k: [x[0], x[1], x[2], x[3]],
        case_k: x[4],
        lead_k: [x[5], x[6], x[7], x[8]],
    };
    if !nodes
        .junction_k
        .iter()
        .chain(nodes.lead_k.iter())
        .all(|v| v.is_finite())
        || !nodes.case_k.is_finite()
    {
        bail!("non-finite package solution");
    }
    Ok(nodes)
}

/// Independently evaluate every node KCL and the case sink reaction.
pub fn balances(
    nodes: &Nodes,
    outward: [f64; 4],
    diode_power_w: [f64; 4],
    weak: bool,
) -> Result<Balances> {
    balances_at_sink(nodes, outward, diode_power_w, weak, AMBIENT_K)
}

/// Independently evaluate balances against an explicit sink temperature.
pub fn balances_at_sink(
    nodes: &Nodes,
    outward: [f64; 4],
    diode_power_w: [f64; 4],
    weak: bool,
    sink_k: f64,
) -> Result<Balances> {
    if !sink_k.is_finite() || sink_k <= 0.0 {
        bail!("sink temperature must be finite");
    }
    if !nodes
        .junction_k
        .iter()
        .chain(nodes.lead_k.iter())
        .all(|v| v.is_finite())
        || !nodes.case_k.is_finite()
    {
        bail!("nodes must be finite");
    }
    if !diode_power_w.iter().all(|v| v.is_finite() && *v >= 0.0)
        || (diode_power_w.iter().sum::<f64>() - EXPECTED_POWER_W).abs() > 1e-8
    {
        bail!("diode power must be finite, non-negative, and sum to 40 W");
    }
    if !outward.iter().all(|v| v.is_finite()) {
        bail!("outward power must be finite");
    }
    let link = if weak { 0.05 } else { 0.1 };
    let gjc = if weak { 1.0 / 1.5 } else { 1.0 };
    let gcs = if weak { 1.0 / 0.5 } else { 1.0 / 0.25 };
    let mut lead_residual_w = [0.0; 4];
    for i in 0..4 {
        // `outward` is the actual FEM heat flow into this package lead.  The
        // old/g terms used to linearize the solve are intentionally absent.
        let mut r = -outward[i];
        for (j, &(u, v)) in EDGES.iter().enumerate() {
            if u == i || v == i {
                r += link * (nodes.lead_k[i] - nodes.junction_k[j]);
            }
        }
        lead_residual_w[i] = r;
    }
    let mut junction_residual_w = [0.0; 4];
    for j in 0..4 {
        let (u, v) = EDGES[j];
        junction_residual_w[j] = diode_power_w[j]
            + link * (nodes.lead_k[u] - nodes.junction_k[j])
            + link * (nodes.lead_k[v] - nodes.junction_k[j])
            + gjc * (nodes.case_k - nodes.junction_k[j]);
    }
    let case_residual_w = (0..4)
        .map(|j| gjc * (nodes.junction_k[j] - nodes.case_k))
        .sum::<f64>()
        + gcs * (sink_k - nodes.case_k);
    Ok(Balances {
        lead_residual_w,
        junction_residual_w,
        case_residual_w,
        sink_w: gcs * (nodes.case_k - sink_k),
    })
}

fn validate_inputs(old: [f64; 4], outward: [f64; 4], g: [f64; 4], p: [f64; 4]) -> Result<()> {
    if !old
        .iter()
        .chain(outward.iter())
        .chain(g.iter())
        .chain(p.iter())
        .all(|v| v.is_finite())
    {
        bail!("inputs must be finite");
    }
    if g.iter().any(|v| *v <= 0.0)
        || p.iter().any(|v| *v < 0.0)
        || (p.iter().sum::<f64>() - EXPECTED_POWER_W).abs() > 1e-8
    {
        bail!("invalid conductance or diode power");
    }
    Ok(())
}

fn gaussian_solve(mut a: [[f64; 9]; 9], mut b: [f64; 9]) -> Result<[f64; 9]> {
    for k in 0..9 {
        let mut pivot = k;
        for i in (k + 1)..9 {
            if a[i][k].abs() > a[pivot][k].abs() {
                pivot = i;
            }
        }
        if !a[pivot][k].is_finite() || a[pivot][k].abs() < 1e-14 {
            bail!("singular package network");
        }
        if pivot != k {
            a.swap(k, pivot);
            b.swap(k, pivot);
        }
        for i in (k + 1)..9 {
            let f = a[i][k] / a[k][k];
            let pivot_row = a[k];
            for (target, pivot) in a[i][k..].iter_mut().zip(&pivot_row[k..]) {
                *target -= f * pivot;
            }
            b[i] -= f * b[k];
        }
    }
    let mut x = [0.0; 9];
    for i in (0..9).rev() {
        let mut s = b[i];
        for j in (i + 1)..9 {
            s -= a[i][j] * x[j];
        }
        x[i] = s / a[i][i];
    }
    Ok(x)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn symmetric_case_matches_closed_form() {
        let n = solve([333.15; 4], [0.0; 4], [0.1; 4], [10.0; 4], false).unwrap();
        assert!((n.junction_k[0] - 350.7970588235294).abs() < 1e-9);
        assert!((n.case_k - 341.9735294117647).abs() < 1e-9);
        assert!((n.lead_k[0] - 344.9147058823529).abs() < 1e-9);
    }

    #[test]
    fn asymmetric_network_closes_each_independent_port() {
        let n = solve(
            [333.15, 334.15, 332.15, 333.65],
            [1.0, -2.0, 3.0, 4.0],
            [0.1; 4],
            [4.0, 6.0, 12.0, 18.0],
            false,
        )
        .unwrap();
        let actual_outward = [
            1.0 + 0.1 * (333.15 - n.lead_k[0]),
            -2.0 + 0.1 * (334.15 - n.lead_k[1]),
            3.0 + 0.1 * (332.15 - n.lead_k[2]),
            4.0 + 0.1 * (333.65 - n.lead_k[3]),
        ];
        let b = balances(&n, actual_outward, [4.0, 6.0, 12.0, 18.0], false).unwrap();
        assert!(b.lead_residual_w.iter().all(|v| v.abs() < 1e-10));
        assert!(b.junction_residual_w.iter().all(|v| v.abs() < 1e-10));
        assert!(b.case_residual_w.abs() < 1e-10);
        assert!((b.sink_w - 40.0 - actual_outward.iter().sum::<f64>()).abs() < 1e-10);
    }

    #[test]
    fn unequal_ports_recover_independently_constructed_node_temperatures() {
        // Choose temperatures first, then calculate each diode loss and port
        // reaction directly. This reference does not invoke matrix assembly.
        let lead = [353.65, 351.15, 356.15, 351.65];
        let p = [8.95, 9.65, 11.55, 9.85];
        let outward = [0.2, -0.4, 0.6, -0.4];
        let n = solve(lead, outward, [0.02, 0.07, 0.15, 0.23], p, false).unwrap();
        for (a, b) in n.junction_k.iter().zip([352.15, 353.15, 354.15, 353.15]) {
            assert!((a - b).abs() < 1e-9);
        }
        assert!((n.case_k - 343.15).abs() < 1e-9);
        for (a, b) in n.lead_k.iter().zip(lead) {
            assert!((a - b).abs() < 1e-9);
        }
        let shifted = solve_at_sink(
            lead.map(|x| x + 40.0),
            outward,
            [0.02, 0.07, 0.15, 0.23],
            p,
            false,
            373.15,
        )
        .unwrap();
        assert!((shifted.case_k - n.case_k - 40.0).abs() < 1e-9);
    }

    #[test]
    fn rejects_nonfinite_and_wrong_power() {
        assert!(solve([f64::NAN; 4], [0.0; 4], [0.1; 4], [10.0; 4], false).is_err());
        assert!(solve([60.0; 4], [0.0; 4], [0.1; 4], [9.0; 4], false).is_err());
        assert!(solve([60.0; 4], [0.0; 4], [0.0; 4], [10.0; 4], false).is_err());
    }
}
