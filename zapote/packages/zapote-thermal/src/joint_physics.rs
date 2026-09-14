//! Verify Elmer's raw quantities independently of its successful exit code.
use crate::joint_fem::{JointInput, MeshStats, SolverMeasurement};
use anyhow::{ensure, Context, Result};
use std::collections::BTreeMap;

const COLUMNS: [&str; 12] = [
    "max: temperature",
    "min: temperature",
    "boundary int: potential over bc 1",
    "boundary int:  over bc 2",
    "boundary int:  over bc 3",
    "area: potential over bc 1",
    "area:  over bc 2",
    "area:  over bc 3",
    "res: total joule heating",
    "res: temperature flux over bc 1",
    "res: temperature flux over bc 2",
    "res: temperature flux over bc 3",
];

fn scalars(names: &str, data: &str) -> Result<[f64; 12]> {
    let (_, body) = names
        .split_once("Variables in columns of matrix:")
        .context("missing scalar column header")?;
    let mut columns = BTreeMap::new();
    for line in body.lines().filter(|l| !l.trim().is_empty()) {
        let (id, label) = line.split_once(':').context("malformed scalar name")?;
        let id: usize = id.trim().parse()?;
        ensure!(
            (1..=12).contains(&id) && columns.insert(id, label.trim()).is_none(),
            "invalid/duplicate scalar index"
        );
    }
    ensure!(
        columns.len() == 12
            && COLUMNS
                .iter()
                .enumerate()
                .all(|(i, c)| columns.get(&(i + 1)) == Some(c)),
        "unexpected scalar names/order"
    );
    let mut rows = data.lines().filter(|l| !l.trim().is_empty());
    let row = rows.next().context("missing scalar row")?;
    ensure!(rows.next().is_none(), "expected one scalar row");
    let values = row
        .split_whitespace()
        .map(str::parse::<f64>)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    ensure!(
        values.len() == 12 && values.iter().all(|v| v.is_finite()),
        "expected twelve finite scalars"
    );
    values
        .try_into()
        .map_err(|_| anyhow::anyhow!("scalar count changed"))
}

fn convergence(log: &str) -> Result<()> {
    ensure!(
        log.contains("MAIN: *** Elmer Solver: ALL DONE ***")
            && !["ERROR::", "FATAL", "DIVERGED", "NOT CONVERGED"]
                .iter()
                .any(|s| log.contains(s)),
        "solver failed or did not finish"
    );
    let mut last = BTreeMap::new();
    for line in log.lines() {
        let Some((_, tail)) = line.split_once("SS (ITER=") else {
            continue;
        };
        let (iteration, _) = tail.split_once(')').context("malformed iteration number")?;
        let iteration: usize = iteration.parse()?;
        let (_, rest) = tail
            .split_once("(NRM,RELC):")
            .context("missing coupled convergence values")?;
        let (values, solver) = rest.split_once("::").context("missing solver identity")?;
        let solver = solver.trim();
        if !["stat current", "heat equation"].contains(&solver) {
            continue;
        }
        let values = values
            .trim()
            .trim_start_matches('(')
            .trim_end_matches(')')
            .split_whitespace()
            .map(str::parse::<f64>)
            .collect::<std::result::Result<Vec<_>, _>>()?;
        ensure!(
            values.len() == 2 && values.iter().all(|v| v.is_finite() && *v >= 0.0),
            "invalid coupled convergence record"
        );
        if let Some((previous, _)) = last.get(solver) {
            ensure!(
                iteration > *previous,
                "duplicate/reversed convergence history"
            );
        }
        last.insert(solver, (iteration, values[1]));
    }
    let electrical = last
        .get("stat current")
        .context("missing electrical steady-state convergence")?;
    let thermal = last
        .get("heat equation")
        .context("missing thermal steady-state convergence")?;
    ensure!(
        electrical.0 == thermal.0
            && (1..30).contains(&thermal.0)
            && electrical.1 <= 1e-8
            && thermal.1 <= 1e-8,
        "coupled electrical/thermal solve did not converge before iteration limit"
    );
    Ok(())
}

/// Recompute input I·V and summed outward heat; retain individual port fluxes.
/// Elmer's reactions are inward-positive. Board ports share edge nodes, so
/// only their sum is meaningful. The isolated lead port has no shared nodes.
pub fn validate(
    log: &str,
    data: &str,
    names: &str,
    input: &JointInput,
    mesh: &MeshStats,
) -> Result<SolverMeasurement> {
    input.validate()?;
    convergence(log)?;
    let v = scalars(names, data)?;
    for (column, id) in [(5, 11), (6, 12), (7, 14)] {
        let area = *mesh
            .port_areas_m2
            .get(&id)
            .context("missing independent port area")?;
        ensure!(
            area.is_finite() && area > 0.0 && (v[column] / area - 1.0).abs() < 1e-7,
            "solver port area differs from mesh"
        );
    }
    ensure!(v[0] >= v[1] && v[1] > 0.0, "invalid temperature envelope");
    let cold = input.package_temperature_k.min(input.board_temperature_k);
    let hot = input.package_temperature_k.max(input.board_temperature_k);
    ensure!(
        v[1] >= cold - 1e-4 && v[1] <= cold + 1e-4 && v[0] >= hot - 1e-4,
        "temperature boundaries/passive minimum inconsistent"
    );
    ensure!(
        v[4].abs() < 1e-14,
        "grounded copper port has nonzero potential"
    );
    let area = mesh.port_areas_m2[&11];
    let iv = input.current_a * v[2] / area;
    let joule = v[8];
    let flux = [v[9], v[10], v[11]];
    let outward = -flux.iter().sum::<f64>();
    ensure!(iv.is_finite() && joule >= 0.0, "invalid electrical power");
    let tolerance = 1e-9 + 5e-5 * joule.abs();
    ensure!(
        (iv - joule).abs() <= tolerance,
        "input I*V and Joule heating disagree"
    );
    ensure!(
        (outward - joule).abs() <= tolerance,
        "outward heat and Joule heating disagree"
    );
    if input.current_a == 0.0 {
        ensure!(
            joule.abs() < 1e-10 && v[2].abs() < 1e-14 && v[0] <= hot + 1e-4,
            "zero current introduces fictitious heating"
        );
    } else {
        ensure!(
            iv > 0.0 && joule > 0.0,
            "positive current requires positive input/Joule power"
        );
    }
    Ok(SolverMeasurement {
        max_temperature_k: v[0],
        min_temperature_k: v[1],
        joule_w: joule,
        flux_w: flux,
        input_iv_w: iv,
        converged: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs, path::PathBuf};
    fn reference() -> (JointInput, MeshStats, String, String, String) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../thermal/physical-model/joint-fem/reference-rect");
        let input = JointInput::default();
        let mesh =
            crate::joint_mesh::parse(&fs::read_to_string(root.join("joint.msh")).unwrap(), &input)
                .unwrap();
        (
            input,
            mesh,
            fs::read_to_string(root.join("elmersolver.log")).unwrap(),
            fs::read_to_string(root.join("scalars.dat")).unwrap(),
            fs::read_to_string(root.join("scalars.dat.names")).unwrap(),
        )
    }
    #[test]
    fn independent_reference_matches_electrical_and_heat_balance() {
        let (i, m, l, s, n) = reference();
        let v = validate(&l, &s, &n, &i, &m).unwrap();
        assert!((v.input_iv_w - 0.2819166834544688).abs() < 1e-10);
    }
    #[test]
    fn changed_voltage_cannot_reuse_joule_power_as_its_own_oracle() {
        let (i, m, l, s, n) = reference();
        let mut v: Vec<f64> = s.split_whitespace().map(|s| s.parse().unwrap()).collect();
        v[2] *= 2.0;
        let s = v
            .iter()
            .map(ToString::to_string)
            .collect::<Vec<_>>()
            .join(" ");
        assert!(validate(&l, &s, &n, &i, &m)
            .unwrap_err()
            .to_string()
            .contains("I*V"));
    }
    #[test]
    fn relative_change_text_without_convergence_is_rejected() {
        let (i, m, _, s, n) = reference();
        assert!(validate(
            "Relative Change : 0\nMAIN: *** Elmer Solver: ALL DONE ***",
            &s,
            &n,
            &i,
            &m
        )
        .is_err());
    }
    #[test]
    fn reordered_flux_labels_are_rejected() {
        let (i, m, l, s, n) = reference();
        assert!(validate(
            &l,
            &s,
            &n.replace("flux over bc 1", "flux over bc 2"),
            &i,
            &m
        )
        .is_err());
    }
}
