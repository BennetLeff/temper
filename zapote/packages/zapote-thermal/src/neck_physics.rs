//! SIF generation and evidence checks for a copper/FR-4 power-entry neck.
//!
//! This module deliberately does not decide whether a PCB is safe.  It binds
//! the numerical values emitted by Elmer to the independent mesh areas and to
//! the boundary conditions used to generate the solve, then reports residuals
//! for review by the harness.

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};

const COLUMN_COUNT: usize = 15;
const CONVERGENCE_TOLERANCE: f64 = 1.0e-8;
const AREA_RELATIVE_TOLERANCE: f64 = 1.0e-7;
const ENERGY_RELATIVE_TOLERANCE: f64 = 1.0e-4;
const ENERGY_ABSOLUTE_TOLERANCE_W: f64 = 1.0e-4;
const FLUX_ABSOLUTE_TOLERANCE_W: f64 = 2.5e-4;

/// Material and boundary parameters for a neck solve.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct Params {
    pub current_a: f64,
    pub ambient_k: f64,
    pub terminal_k: f64,
    pub board_k: f64,
    pub convection_w_m2k: f64,
    pub terminal_conductance_w_k: f64,
    pub board_conductance_w_k: f64,
    pub conductivity_s_m: f64,
    pub alpha_per_k: f64,
    pub copper_k_w_mk: f64,
    pub fr4_k_w_mk: f64,
}

/// Areas of the three mesh boundary groups: terminal, board, and exposed FR-4.
pub type BoundaryAreas = [f64; 3];

/// Numerically checked scalar output.  Residuals are retained so callers can
/// apply their own engineering limits without conflating them with parsing.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Measurement {
    pub max_temperature_k: f64,
    pub min_temperature_k: f64,
    pub boundary_temperature_integrals_k_m2: [f64; 3],
    pub boundary_areas_m2: [f64; 3],
    pub boundary_mean_temperature_k: [f64; 3],
    pub boundary_potential_integrals_v_m: [f64; 3],
    pub joule_power_w: f64,
    pub boundary_temperature_flux_w: [f64; 3],
    pub heat_flows_out_w: [f64; 3],
    pub voltage_drop_v: f64,
    pub resistance_ohm: f64,
    pub energy_balance_residual_w: f64,
    pub flux_residuals_w: [f64; 3],
    pub electrical_residual_w: f64,
    pub converged_iterations: usize,
    pub terminal_relative_change: Option<f64>,
    pub assumptions: Vec<String>,
}

fn finite_positive(name: &str, value: f64) -> Result<()> {
    if !value.is_finite() || value <= 0.0 {
        bail!("{name} must be finite and positive");
    }
    Ok(())
}

fn validate_inputs(params: &Params, areas: BoundaryAreas) -> Result<()> {
    finite_positive("current_a", params.current_a)?;
    for (name, value) in [
        ("ambient_k", params.ambient_k),
        ("terminal_k", params.terminal_k),
        ("board_k", params.board_k),
        ("conductivity_s_m", params.conductivity_s_m),
        ("copper_k_w_mk", params.copper_k_w_mk),
        ("fr4_k_w_mk", params.fr4_k_w_mk),
    ] {
        finite_positive(name, value)?;
    }
    finite_positive("convection_w_m2k", params.convection_w_m2k)?;
    finite_positive("terminal_conductance_w_k", params.terminal_conductance_w_k)?;
    finite_positive("board_conductance_w_k", params.board_conductance_w_k)?;
    if !params.alpha_per_k.is_finite() || params.alpha_per_k < 0.0 || params.alpha_per_k >= 1.0 {
        bail!("alpha_per_k must be finite and in [0, 1)/K for copper");
    }
    for (index, area) in areas.into_iter().enumerate() {
        finite_positive(&format!("boundary area {index}"), area)?;
    }
    Ok(())
}

/// Generate a coupled copper/FR-4 SIF using physical boundary areas.
pub fn sif(params: &Params, areas: BoundaryAreas) -> Result<String> {
    validate_inputs(params, areas)?;
    let [area_terminal, area_board, _area_fr4] = areas;
    let terminal_h = params.terminal_conductance_w_k / area_terminal;
    let board_h = params.board_conductance_w_k / area_board;
    let current_density = params.current_a / area_terminal;
    Ok(format!(
        r#"Header
 CHECK KEYWORDS Warn
 Mesh DB "." "neck"
End
Simulation
 Coordinate System = Cartesian 3D
 Simulation Type = Steady State
 Steady State Max Iterations = 30
 Output Intervals = 1
 Post File = "neck.vtu"
End
Body 1
 Target Bodies(1) = 1
 Equation = 1
 Material = 1
 Body Force = 1
 Initial Condition = 1
End
Body 2
 Target Bodies(1) = 2
 Equation = 2
 Material = 2
 Initial Condition = 1
End
Initial Condition 1
 Temperature = {:.12}
End
Equation 1
 Active Solvers(3) = 1 2 3
End
Equation 2
 Active Solvers(2) = 2 3
End
Solver 1
 Equation = Stat Current
 Procedure = "StatCurrentSolve" "StatCurrentSolver"
 Variable = Potential
 Variable DOFs = 1
 Calculate Volume Current = True
 Calculate Joule Heating = True
 Linear System Solver = Direct
 Linear System Direct Method = umfpack
 Nonlinear System Max Iterations = 1
 Steady State Convergence Tolerance = 1e-8
End
Solver 2
 Equation = Heat Equation
 Procedure = "HeatSolve" "HeatSolver"
 Variable = Temperature
 Linear System Solver = Direct
 Linear System Direct Method = umfpack
 Nonlinear System Max Iterations = 1
 Steady State Convergence Tolerance = 1e-8
 Calculate Loads = True
 Calculate Boundary Fluxes = True
End
Solver 3
 Exec Solver = After All
 Equation = SaveScalars
 Procedure = "SaveData" "SaveScalars"
 Variable 1 = Temperature
 Operator 1 = max
 Variable 2 = Temperature
 Operator 2 = min
 Variable 3 = Temperature
 Operator 3 = boundary int
 Variable 4 = Temperature
 Operator 4 = area
 Variable 5 = Potential
 Operator 5 = boundary int
 Filename = "scalars.dat"
End
Material 1
 Electric Conductivity = Variable Temperature
  Real MATC "{sigma:.12e}/(1+{alpha:.12e}*(tx-293.15))"
 Heat Conductivity = {copper_k:.12}
 Density = 8960.0
 Heat Capacity = 385.0
End
Material 2
 Heat Conductivity = {fr4_k:.12}
 Density = 1900.0
 Heat Capacity = 1000.0
End
Body Force 1
 Joule Heat = True
End
Boundary Condition 1
 Target Boundaries(1) = 11
 Current Density BC = True
 Current Density = {current_density:.12e}
 Heat Transfer Coefficient = {terminal_h:.12e}
 External Temperature = {terminal:.12}
 Save Scalars = True
End
Boundary Condition 2
 Target Boundaries(1) = 12
 Potential = 0.0
 Heat Transfer Coefficient = {board_h:.12e}
 External Temperature = {board:.12}
 Save Scalars = True
End
Boundary Condition 3
 Target Boundaries(1) = 13
 Heat Transfer Coefficient = {convection:.12e}
 External Temperature = {ambient:.12}
 Save Scalars = True
End
"#,
        params.ambient_k,
        sigma = params.conductivity_s_m,
        alpha = params.alpha_per_k,
        copper_k = params.copper_k_w_mk,
        fr4_k = params.fr4_k_w_mk,
        current_density = current_density,
        terminal_h = terminal_h,
        terminal = params.terminal_k,
        board_h = board_h,
        board = params.board_k,
        convection = params.convection_w_m2k,
        ambient = params.ambient_k,
    ))
}

const EXPECTED_COLUMNS: [&str; COLUMN_COUNT] = [
    "max: temperature",
    "min: temperature",
    "boundary int: temperature over bc 1",
    "boundary int:  over bc 2",
    "boundary int:  over bc 3",
    "area: temperature over bc 1",
    "area:  over bc 2",
    "area:  over bc 3",
    "boundary int: potential over bc 1",
    "boundary int:  over bc 2",
    "boundary int:  over bc 3",
    "res: total joule heating",
    "res: temperature flux over bc 1",
    "res: temperature flux over bc 2",
    "res: temperature flux over bc 3",
];

fn parse_columns(names: &str) -> Result<()> {
    let (_, body) = names
        .split_once("Variables in columns of matrix:")
        .context("missing scalar column header")?;
    let mut parsed = Vec::new();
    for line in body.lines().filter(|line| !line.trim().is_empty()) {
        let (index, label) = line.split_once(':').context("malformed scalar name row")?;
        let index: usize = index
            .trim()
            .parse()
            .context("invalid scalar column index")?;
        if index == 0 || index > COLUMN_COUNT || parsed.iter().any(|(i, _)| *i == index) {
            bail!("invalid or duplicate scalar column index");
        }
        parsed.push((index, label.trim().to_owned()));
    }
    parsed.sort_by_key(|(index, _)| *index);
    if parsed.len() != COLUMN_COUNT
        || parsed
            .iter()
            .zip(EXPECTED_COLUMNS)
            .any(|((index, label), expected)| *index == 0 || label != expected)
    {
        bail!("unexpected scalar column names");
    }
    Ok(())
}

fn parse_scalar_row(scalars: &str) -> Result<[f64; COLUMN_COUNT]> {
    let rows: Vec<_> = scalars
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    if rows.len() != 1 {
        bail!("expected exactly one scalar row");
    }
    let values = rows[0]
        .split_whitespace()
        .map(str::parse::<f64>)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if values.len() != COLUMN_COUNT || values.iter().any(|value| !value.is_finite()) {
        bail!("expected fifteen finite scalar values");
    }
    values
        .try_into()
        .map_err(|_| anyhow::anyhow!("scalar column count changed"))
}

fn logged_values(log: &str, label: &str) -> Result<Vec<f64>> {
    let mut values = Vec::new();
    for line in log.lines() {
        let Some((_, rest)) = line.split_once(label) else {
            continue;
        };
        let value: f64 = rest
            .trim()
            .strip_prefix(':')
            .context("malformed logged scalar")?
            .trim()
            .parse()
            .context("malformed logged scalar")?;
        values.push(value);
        values.push(value);
    }
    if values.is_empty() || values.iter().any(|value| !value.is_finite()) {
        bail!("missing or non-finite logged {label}");
    }
    Ok(values)
}

fn convergence(log: &str) -> Result<(usize, Option<f64>)> {
    let iterations = log.matches("TEMPERATURE ITERATION").count();
    if iterations == 0 || iterations >= 30 {
        bail!("temperature solve lacks a bounded steady-state iteration history");
    }
    let mut changes = Vec::new();
    for line in log.lines() {
        let Some((_, rest)) = line.split_once("Relative Change") else {
            continue;
        };
        let value: f64 = rest
            .trim()
            .strip_prefix(':')
            .context("malformed temperature relative change")?
            .trim()
            .parse()
            .context("malformed temperature relative change")?;
        changes.push(value);
    }
    if changes.is_empty() {
        bail!("temperature solve lacks a terminal relative-change record");
    }
    if changes.iter().any(|value| !value.is_finite()) {
        bail!("non-finite temperature relative change");
    }
    let terminal = changes.last().copied();
    if let Some(value) = terminal {
        if value > CONVERGENCE_TOLERANCE {
            bail!("terminal temperature relative change is not converged");
        }
    }
    Ok((iterations, terminal))
}

fn close_enough(actual: f64, expected: f64, relative: f64, absolute: f64) -> bool {
    (actual - expected).abs() <= absolute.max(relative * expected.abs())
}

/// Parse and independently validate a coupled neck result.
pub fn parse_validate(
    log: &[u8],
    scalars: &[u8],
    names: &[u8],
    params: &Params,
    expected_areas: BoundaryAreas,
) -> Result<Measurement> {
    validate_inputs(params, expected_areas)?;
    let log = std::str::from_utf8(log).context("Elmer log is not UTF-8")?;
    let scalars = std::str::from_utf8(scalars).context("scalar data is not UTF-8")?;
    let names = std::str::from_utf8(names).context("scalar names are not UTF-8")?;
    if !log.contains("MAIN: *** Elmer Solver: ALL DONE ***") {
        bail!("missing Elmer completion marker");
    }
    parse_columns(names)?;
    let values = parse_scalar_row(scalars)?;
    let [max_temperature, min_temperature, p1, p2, p3, a1, a2, a3, v1, v2, v3, power, f1, f2, f3] =
        values;
    if min_temperature <= 0.0 || max_temperature < min_temperature || power <= 0.0 {
        bail!("temperature extrema are not physical");
    }
    let reservoir_floor = params.ambient_k.min(params.terminal_k).min(params.board_k);
    if min_temperature < reservoir_floor - 1.0e-6 {
        bail!("minimum temperature is below all passive reservoirs");
    }
    let areas = [a1, a2, a3];
    for (index, (actual, expected)) in areas.iter().zip(expected_areas).enumerate() {
        if !close_enough(*actual, expected, AREA_RELATIVE_TOLERANCE, 0.0) {
            bail!("boundary area {index} disagrees with independent mesh area");
        }
    }
    let temp_integrals = [p1, p2, p3];
    let means = std::array::from_fn(|index| temp_integrals[index] / areas[index]);
    if means
        .iter()
        .any(|mean| *mean < min_temperature || *mean > max_temperature)
    {
        bail!("boundary temperature mean lies outside extrema");
    }
    let logged_power = logged_values(log, "Total Heating Power")?
        .last()
        .copied()
        .context("missing final heating power")?;
    if !close_enough(
        logged_power,
        power,
        ENERGY_RELATIVE_TOLERANCE,
        ENERGY_ABSOLUTE_TOLERANCE_W,
    ) {
        bail!("scalar joule power disagrees with final solver log");
    }
    if v2.abs() > 1.0e-9 {
        bail!("zero-potential boundary integral is not near zero");
    }
    let h = [
        params.terminal_conductance_w_k / areas[0],
        params.board_conductance_w_k / areas[1],
        params.convection_w_m2k,
    ];
    let external = [params.terminal_k, params.board_k, params.ambient_k];
    let heat_flows_out = std::array::from_fn(|index| {
        h[index] * (temp_integrals[index] - areas[index] * external[index])
    });
    let energy_residual = heat_flows_out.iter().sum::<f64>() - power;
    if !close_enough(
        energy_residual,
        0.0,
        ENERGY_RELATIVE_TOLERANCE,
        ENERGY_ABSOLUTE_TOLERANCE_W,
    ) {
        bail!("Robin boundary energy does not balance joule heating");
    }
    let fluxes = [f1, f2, f3];
    let flux_residuals = std::array::from_fn(|index| fluxes[index] + heat_flows_out[index]);
    // Elmer SolverUtils::CalculateLoads assigns a shared boundary node's
    // reaction to the first encountered BC. Individual RES flux groups thus
    // depend on boundary traversal at corners; only their sum is conservative.
    // The separate Robin integrals above supply the physical per-face heat.
    if (fluxes.iter().sum::<f64>() + power).abs() > FLUX_ABSOLUTE_TOLERANCE_W {
        bail!("total nodal boundary heat flux does not balance joule heating");
    }
    let voltage_drop = v1 / areas[0];
    if voltage_drop <= 0.0 {
        bail!("current boundary potential drop is not positive");
    }
    let electrical_power = params.current_a * voltage_drop;
    let electrical_residual = electrical_power - power;
    if !close_enough(
        electrical_residual,
        0.0,
        ENERGY_RELATIVE_TOLERANCE,
        ENERGY_ABSOLUTE_TOLERANCE_W,
    ) {
        bail!("current and potential drop do not reproduce joule power");
    }
    let (iterations, terminal_relative_change) = convergence(log)?;
    Ok(Measurement {
        max_temperature_k: max_temperature,
        min_temperature_k: min_temperature,
        boundary_temperature_integrals_k_m2: temp_integrals,
        boundary_areas_m2: areas,
        boundary_mean_temperature_k: means,
        boundary_potential_integrals_v_m: [v1, v2, v3],
        joule_power_w: power,
        boundary_temperature_flux_w: fluxes,
        heat_flows_out_w: heat_flows_out,
        voltage_drop_v: voltage_drop,
        resistance_ohm: power / params.current_a.powi(2),
        energy_balance_residual_w: energy_residual,
        flux_residuals_w: flux_residuals,
        electrical_residual_w: electrical_residual,
        converged_iterations: iterations,
        terminal_relative_change,
        assumptions: vec![
            "Boundary 11 current is uniform over its independently supplied area.".into(),
            "Boundary 11/12 conductances are lumped W/K values converted to Robin h by area.".into(),
            "RES fluxes are inward-positive nodal reactions; shared corner nodes make individual BC totals order-dependent. Only their sum is validated. Robin integrals give outward-positive per-face heat.".into(),
        ],
    })
}

/// Independent one-dimensional Robin-bar oracle for a constant conductivity.
///
/// This is intentionally separate from Elmer: it solves the closed-form
/// insulated-cross-section heat equation with side convection and lumped end
/// conductances.  It is a corroboration check for the simple bar fixture, not
/// a PCB acceptance criterion.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ClosedFormBar {
    pub power_w: f64,
    pub max_temperature_k: f64,
    pub min_temperature_k: f64,
}

pub fn constant_robin_bar_oracle(
    params: &Params,
    length_m: f64,
    width_m: f64,
    height_m: f64,
) -> Result<ClosedFormBar> {
    validate_inputs(params, [1.0, 1.0, 1.0])?;
    finite_positive("length_m", length_m)?;
    finite_positive("width_m", width_m)?;
    finite_positive("height_m", height_m)?;
    let area = width_m * height_m;
    let perimeter = 2.0 * (width_m + height_m);
    let resistance = length_m / (params.conductivity_s_m * area);
    let power = params.current_a.powi(2) * resistance;
    let side_h = params.convection_w_m2k;
    let k_a = params.copper_k_w_mk * area;
    let m = (side_h * perimeter / k_a).sqrt();
    let theta_p = power / (length_m * side_h * perimeter);
    let g0 = params.terminal_conductance_w_k;
    let g1 = params.board_conductance_w_k;
    let ml = m * length_m;
    let sinh = ml.sinh();
    let cosh = ml.cosh();
    let km = k_a * m;
    let a11 = -g0;
    let a12 = km;
    let a21 = km * sinh + g1 * cosh;
    let a22 = km * cosh + g1 * sinh;
    // Boundary 11 is tied to a terminal at `terminal_k`, so its Robin
    // equation is written relative to ambient as theta(0)-DeltaT_terminal.
    let b1 = g0 * (theta_p - (params.terminal_k - params.ambient_k));
    let b2 = -g1 * theta_p;
    let determinant = a11 * a22 - a12 * a21;
    if !determinant.is_finite() || determinant.abs() < f64::EPSILON {
        bail!("closed-form Robin system is singular");
    }
    let c = (b1 * a22 - a12 * b2) / determinant;
    let d = (a11 * b2 - b1 * a21) / determinant;
    let left = params.ambient_k + theta_p + c;
    let right = params.ambient_k + theta_p + c * cosh + d * sinh;
    let center = params.ambient_k + theta_p + c * (ml / 2.0).cosh() + d * (ml / 2.0).sinh();
    Ok(ClosedFormBar {
        power_w: power,
        max_temperature_k: left.max(right).max(center),
        min_temperature_k: left.min(right).min(center),
    })
}
