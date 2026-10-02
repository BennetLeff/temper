//! Versioned batch interface with separate metrics, budgets and coverage.
//! Budget status concerns only the declared model. It is never board approval.
use super::{
    assembly, capacitance, copper, coupling, decoupling, ensure, finite, identities, nonnegative,
    returns, thermal, Error,
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

/// The nine independent tuning families.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Family {
    /// Oriented power-loop to gate-loop induced EMF.
    GateCoupling,
    /// Input-referred Kelvin sensing error.
    KelvinSense,
    /// Broadside switch-node capacitive coupling screen.
    SwitchCoupling,
    /// Independent series-RLC supply branch impedance.
    Decoupling,
    /// Return-path detour and common impedance.
    ReturnPath,
    /// Explicit DC copper-network sharing and losses.
    CopperDistribution,
    /// Magnetic/electric bypass around an EMI filter.
    EmiBypass,
    /// Assembly-specific linear thermal influence and drift.
    ThermalInfluence,
    /// Worst-case assembly/access envelope separation.
    AssemblyMargin,
}

/// Parameters for one operating-point or geometry comparison.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(
    tag = "kind",
    content = "parameters",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum Scenario {
    /// Signed mutuals and simultaneous current slews.
    GateCoupling(Vec<coupling::InductiveTerm>),
    /// Differential sense-input model.
    KelvinSense(coupling::KelvinInput),
    /// Homogeneous-dielectric rectangle overlap screen.
    SwitchCoupling {
        /// Disjoint actual filled rectangular patches on the aggressor.
        aggressors: Vec<capacitance::Patch>,
        /// Disjoint actual filled rectangular patches on the victim.
        victims: Vec<capacitance::Patch>,
        /// Relative permittivity of the intervening homogeneous dielectric.
        relative_permittivity: f64,
        /// Magnitude of differential switching slew, V/ns.
        slew_v_per_ns: f64,
    },
    /// Supply impedance at explicitly requested frequencies.
    Decoupling {
        /// Independent capacitor/route branches.
        branches: Vec<decoupling::Branch>,
        /// Frequencies, Hz; a finite sweep is not a continuous-band maximum.
        frequencies_hz: Vec<f64>,
    },
    /// Native return path plus shared impedance.
    ReturnPath(returns::Input),
    /// Compact connected DC copper network.
    CopperDistribution {
        /// Node count, 2..=512.
        nodes: usize,
        /// Reference node index.
        ground: usize,
        /// Conducting sections with temperature-specific resistance.
        edges: Vec<copper::Edge>,
        /// Signed, balanced node injections, A.
        injections_a: Vec<f64>,
    },
    /// Conservative independent-sign pickup at the filtered victim port.
    EmiBypass {
        /// Oriented magnetic coupling terms.
        magnetic: Vec<coupling::InductiveTerm>,
        /// Electric coupling terms.
        electric: Vec<coupling::CapacitiveTerm>,
        /// Victim transfer-impedance magnitude bound, ohms, over the scenario.
        transfer_ohm: f64,
    },
    /// Temperature and first-order drift within a declared model domain.
    ThermalInfluence(thermal::Input),
    /// Assembly envelopes and reporting radius.
    AssemblyMargin {
        /// Component/hardware/tool envelopes.
        envelopes: Vec<assembly::Envelope>,
        /// Pairs farther away are not emitted, mm.
        search_distance_mm: f64,
    },
}
impl Scenario {
    /// Family evaluated by this scenario.
    pub fn family(&self) -> Family {
        match self {
            Self::GateCoupling(_) => Family::GateCoupling,
            Self::KelvinSense(_) => Family::KelvinSense,
            Self::SwitchCoupling { .. } => Family::SwitchCoupling,
            Self::Decoupling { .. } => Family::Decoupling,
            Self::ReturnPath(_) => Family::ReturnPath,
            Self::CopperDistribution { .. } => Family::CopperDistribution,
            Self::EmiBypass { .. } => Family::EmiBypass,
            Self::ThermalInfluence(_) => Family::ThermalInfluence,
            Self::AssemblyMargin { .. } => Family::AssemblyMargin,
        }
    }
}

/// The direction of a user-defined engineering budget.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    /// Value must be no greater than the limit.
    Maximum,
    /// Value must be no less than the limit.
    Minimum,
}
/// Budget for an exact named metric; units follow that metric's documented key.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Budget {
    /// Metric key, including its unit suffix.
    pub metric: String,
    /// Desired bound direction.
    pub direction: Direction,
    /// Limit in the metric's units.
    pub limit: f64,
}
/// An independently evaluated case.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Case {
    /// Stable case identity (e.g. leg-A, hard-turn-on).
    pub id: String,
    /// Extraction/model source and applicability; not a qualification claim.
    pub basis: String,
    /// Explicit model assumptions and omitted effects.
    pub assumptions: Vec<String>,
    /// Typed engineering input.
    pub scenario: Scenario,
    /// Optional budgets; no budget means measured model output, not a pass.
    pub budgets: Vec<Budget>,
}
/// Source-bound batch request. The CLI verifies `board_sha256` against saved bytes.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Input {
    /// Schema version; currently 1.
    pub schema_version: u32,
    /// Full lowercase SHA-256 of the board being evaluated.
    pub board_sha256: String,
    /// Source revision used to prepare the scenarios.
    pub source_revision: String,
    /// Required families; missing families are explicit coverage gaps.
    pub required_checks: Vec<Family>,
    /// Cases to evaluate.
    pub cases: Vec<Case>,
}
/// One numeric observation and its optional budget margin.
#[derive(Debug, Clone, Serialize)]
pub struct Metric {
    /// Metric name with unit suffix.
    pub name: String,
    /// Numeric value under the declared model.
    pub value: f64,
    /// Positive means inside budget; absent if no budget was supplied.
    pub margin: Option<f64>,
}
/// Result status for the declared model only.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    /// Valid calculation with no budgets.
    Unscored,
    /// All supplied budgets are met (unbudgeted metrics remain advisory).
    WithinBudgets,
    /// At least one supplied budget is exceeded.
    OutsideBudgets,
    /// Malformed/missing input, unsupported model domain or numerical failure.
    Invalid,
}
/// Per-case report, retaining object-level details and assumptions.
#[derive(Debug, Clone, Serialize)]
pub struct CaseReport {
    /// Case identity.
    pub id: String,
    /// Check family.
    pub family: Family,
    /// Model budget status, not board acceptance.
    pub status: Status,
    /// Source/model basis copied from the request.
    pub basis: String,
    /// Explicit assumptions copied from the request.
    pub assumptions: Vec<String>,
    /// Independent physical metrics; never combined into a weighted score.
    pub metrics: Vec<Metric>,
    /// Typed kernel output serialized without losing object witnesses.
    pub details: serde_json::Value,
    /// Reason when invalid.
    pub error: Option<String>,
}
/// Complete batch output.
#[derive(Debug, Clone, Serialize)]
pub struct Report {
    /// Output schema version.
    pub schema_version: u32,
    /// Source board hash; library callers must verify binding themselves.
    pub board_sha256: String,
    /// Requested source revision.
    pub source_revision: String,
    /// All per-case results, including failures.
    pub cases: Vec<CaseReport>,
    /// Required families without any valid evaluation.
    pub missing_checks: Vec<Family>,
}

fn details(value: impl Serialize) -> Result<serde_json::Value, Error> {
    serde_json::to_value(value).map_err(|e| Error(e.to_string()))
}
fn metric(name: &str, value: f64) -> Result<Metric, Error> {
    Ok(Metric {
        name: name.into(),
        value: finite(value, name)?,
        margin: None,
    })
}
fn evaluate(scenario: &Scenario) -> Result<(Vec<Metric>, serde_json::Value), Error> {
    let mut metrics = Vec::new();
    let detail = match scenario {
        Scenario::GateCoupling(terms) => {
            let result = coupling::induced_voltage(terms)?;
            metrics.push(metric("pickup_magnitude_v", result.signed_v.abs())?);
            metrics.push(metric(
                "independent_sign_bound_v",
                result.independent_sign_bound_v,
            )?);
            details(result)?
        }
        Scenario::KelvinSense(input) => {
            let result = coupling::kelvin_error(input)?;
            metrics.push(metric("sense_error_magnitude_v", result.error_v.abs())?);
            metrics.push(metric(
                "current_error_bound_a",
                result.current_error_bound_a,
            )?);
            details(result)?
        }
        Scenario::SwitchCoupling {
            aggressors,
            victims,
            relative_permittivity,
            slew_v_per_ns,
        } => {
            nonnegative(*slew_v_per_ns, "slew_v_per_ns")?;
            let result = capacitance::broadside(aggressors, victims, *relative_permittivity)?;
            let total = finite(
                result.iter().map(|p| p.capacitance_pf).sum(),
                "total broadside capacitance",
            )?;
            metrics.push(metric("projected_capacitance_pf", total)?);
            metrics.push(metric(
                "projected_displacement_a",
                total * slew_v_per_ns * 1e-3,
            )?);
            details(result)?
        }
        Scenario::Decoupling {
            branches,
            frequencies_hz,
        } => {
            let result = decoupling::sweep(branches, frequencies_hz)?;
            let peak = result.iter().map(|p| p.impedance_ohm).fold(0.0, f64::max);
            metrics.push(metric("sampled_peak_impedance_ohm", peak)?);
            // Keep identities adjacent to indexed participation arrays.
            serde_json::json!({"branch_objects": branches.iter().map(|b| &b.object).collect::<Vec<_>>(), "frequencies": result})
        }
        Scenario::ReturnPath(input) => {
            let result = returns::evaluate(input)?;
            metrics.push(metric("detour_ratio", result.detour_ratio)?);
            metrics.push(metric(
                "shared_voltage_bound_v",
                result.shared_voltage_bound_v,
            )?);
            details(result)?
        }
        Scenario::CopperDistribution {
            nodes,
            ground,
            edges,
            injections_a,
        } => {
            let result = copper::Network::new(*nodes, *ground, edges)?.solve(injections_a)?;
            metrics.push(metric("total_loss_w", result.total_loss_w)?);
            metrics.push(metric(
                "peak_section_current_density_a_per_mm2",
                result
                    .branches
                    .iter()
                    .map(|b| b.current_density_a_per_mm2)
                    .fold(0.0, f64::max),
            )?);
            details(result)?
        }
        Scenario::EmiBypass {
            magnetic,
            electric,
            transfer_ohm,
        } => {
            let voltage = coupling::emi_bypass_voltage(magnetic, electric, *transfer_ohm)?;
            metrics.push(metric("bypass_voltage_bound_v", voltage)?);
            serde_json::json!({"magnetic": coupling::induced_voltage(magnetic)?, "electric_current_a": coupling::displacement_current(electric)?, "magnetic_objects": magnetic.iter().map(|t| &t.object).collect::<Vec<_>>(), "electric_objects": electric.iter().map(|t| &t.object).collect::<Vec<_>>()})
        }
        Scenario::ThermalInfluence(input) => {
            let result = thermal::evaluate(input)?;
            metrics.push(metric("temperature_c", result.temperature_c)?);
            metrics.push(metric("drift_magnitude_ppm", result.drift_ppm.abs())?);
            details(result)?
        }
        Scenario::AssemblyMargin {
            envelopes,
            search_distance_mm,
        } => {
            let result = assembly::nearby(envelopes, *search_distance_mm)?;
            // When no pair is inside the search radius, report only the proven
            // lower bound. Do not fabricate the unmeasured minimum separation.
            metrics.push(metric(
                "minimum_gap_lower_bound_mm",
                result
                    .first()
                    .map_or(*search_distance_mm, |p| p.signed_gap_mm),
            )?);
            details(result)?
        }
    };
    Ok((metrics, detail))
}

/// Evaluate all cases without hiding invalid cases or uncovered families.
///
/// # Errors
/// Rejects malformed batch identity/version, duplicate case IDs and duplicate
/// required families. Case-specific errors are retained in the report instead.
pub fn run(input: &Input) -> Result<Report, Error> {
    ensure(
        input.schema_version == 1,
        "unsupported layout-quality schema version",
    )?;
    ensure(
        input.board_sha256.len() == 64
            && input
                .board_sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "board_sha256 must be a full lowercase SHA-256",
    )?;
    ensure(
        !input.source_revision.trim().is_empty(),
        "source revision is blank",
    )?;
    ensure(
        !input.required_checks.is_empty(),
        "required check population is empty",
    )?;
    let required: BTreeSet<_> = input.required_checks.iter().copied().collect();
    ensure(
        required.len() == input.required_checks.len(),
        "duplicate required check",
    )?;
    identities(input.cases.iter().map(|c| c.id.as_str()))?;
    let mut covered = BTreeSet::new();
    let mut cases = Vec::with_capacity(input.cases.len());
    for c in &input.cases {
        let evaluated = (|| {
            ensure(!c.basis.trim().is_empty(), "model basis is blank")?;
            ensure(
                !c.assumptions.is_empty() && c.assumptions.iter().all(|s| !s.trim().is_empty()),
                "model assumptions are missing",
            )?;
            identities(c.budgets.iter().map(|b| b.metric.as_str()))?;
            let (mut metrics, d) = evaluate(&c.scenario)?;
            let lookup: BTreeMap<_, _> = metrics
                .iter()
                .enumerate()
                .map(|(i, m)| (m.name.clone(), i))
                .collect();
            let mut status = if c.budgets.is_empty() {
                Status::Unscored
            } else {
                Status::WithinBudgets
            };
            for b in &c.budgets {
                finite(b.limit, "budget limit")?;
                ensure(
                    b.metric != "minimum_gap_lower_bound_mm"
                        || matches!(b.direction, Direction::Minimum),
                    "a lower-bound assembly metric only supports a minimum budget",
                )?;
                let index = lookup
                    .get(&b.metric)
                    .ok_or_else(|| Error(format!("unknown metric budget: {}", b.metric)))?;
                let m = &mut metrics[*index];
                let margin = finite(
                    match b.direction {
                        Direction::Maximum => b.limit - m.value,
                        Direction::Minimum => m.value - b.limit,
                    },
                    "budget margin",
                )?;
                if margin < 0.0 {
                    status = Status::OutsideBudgets;
                }
                m.margin = Some(margin);
            }
            Ok::<_, Error>((metrics, d, status))
        })();
        let (metrics, d, status, error) = match evaluated {
            Ok((m, d, s)) => {
                covered.insert(c.scenario.family());
                (m, d, s, None)
            }
            Err(e) => (
                Vec::new(),
                serde_json::Value::Null,
                Status::Invalid,
                Some(e.to_string()),
            ),
        };
        cases.push(CaseReport {
            id: c.id.clone(),
            family: c.scenario.family(),
            status,
            basis: c.basis.clone(),
            assumptions: c.assumptions.clone(),
            metrics,
            details: d,
            error,
        });
    }
    Ok(Report {
        schema_version: 1,
        board_sha256: input.board_sha256.clone(),
        source_revision: input.source_revision.clone(),
        cases,
        missing_checks: required.difference(&covered).copied().collect(),
    })
}
