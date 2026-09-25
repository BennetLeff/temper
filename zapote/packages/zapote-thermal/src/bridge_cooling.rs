//! Cooling-contract wrapper for the power-entry bridge-neck model.
//!
//! The contract records a proposed heatsink/fan assembly and its design
//! targets.  It is intentionally a requirement set, not a datasheet claim:
//! the wrapper reports numerical evidence and budget arithmetic while keeping
//! qualification unverified until the assembly is characterized.

use crate::{neck_physics, neck_run, sha256_file};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path};

pub const CONTRACT_SCHEMA: &str = "zapote.bridge-cooling.contract.v1";
pub const ASSESSMENT_SCHEMA: &str = "zapote.bridge-cooling.assessment.v1";
pub const QUALIFICATION_STATUS: &str = "design_requirements_unverified";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CoolingContract {
    pub schema: String,
    pub board_sha256: String,
    pub heatsink_id: String,
    pub fan_id: String,
    pub fan_quantity: u32,
    pub qualification: String,
    pub current_a: f64,
    pub ambient_c: f64,
    pub bridge_loss_w: f64,
    pub theta_junction_case_c_per_w: f64,
    pub theta_case_sink_c_per_w: f64,
    pub theta_sink_air_c_per_w: f64,
    pub theta_sink_air_failed_fan_c_per_w: f64,
    pub junction_limit_c: f64,
    pub pcb_limit_c: f64,
    pub terminal_limit_c: f64,
    pub board_limit_c: f64,
    pub terminal_conductance_w_per_k: f64,
    pub board_conductance_w_per_k: f64,
}

impl CoolingContract {
    #[cfg(test)]
    fn for_board(board_sha256: impl Into<String>) -> Self {
        let mut contract: Self = serde_json::from_str(include_str!(
            "../../../thermal/bridge-cooling-contract.json"
        ))
        .unwrap();
        contract.board_sha256 = board_sha256.into();
        contract
    }

    fn validate(&self, board_sha256: &str) -> Result<()> {
        if self.schema != CONTRACT_SCHEMA {
            bail!("unsupported cooling contract schema");
        }
        if self.qualification != QUALIFICATION_STATUS {
            bail!("cooling qualification status must remain unverified");
        }
        if self.board_sha256 != board_sha256
            || self.board_sha256.len() != 64
            || !self.board_sha256.bytes().all(|b| b.is_ascii_hexdigit())
        {
            bail!("cooling contract board identity mismatch");
        }
        for (label, value) in [
            ("current_a", self.current_a),
            ("ambient_c", self.ambient_c),
            ("bridge_loss_w", self.bridge_loss_w),
            (
                "theta_junction_case_c_per_w",
                self.theta_junction_case_c_per_w,
            ),
            ("theta_case_sink_c_per_w", self.theta_case_sink_c_per_w),
            ("theta_sink_air_c_per_w", self.theta_sink_air_c_per_w),
            (
                "theta_sink_air_failed_fan_c_per_w",
                self.theta_sink_air_failed_fan_c_per_w,
            ),
            ("junction_limit_c", self.junction_limit_c),
            ("pcb_limit_c", self.pcb_limit_c),
            ("terminal_limit_c", self.terminal_limit_c),
            ("board_limit_c", self.board_limit_c),
            (
                "terminal_conductance_w_per_k",
                self.terminal_conductance_w_per_k,
            ),
            ("board_conductance_w_per_k", self.board_conductance_w_per_k),
        ] {
            if !value.is_finite() || value <= 0.0 {
                bail!("cooling contract {label} must be finite and positive");
            }
        }
        for (label, value, maximum) in [
            ("junction_limit_c", self.junction_limit_c, 125.0),
            ("pcb_limit_c", self.pcb_limit_c, 110.0),
            ("terminal_limit_c", self.terminal_limit_c, 110.0),
            ("board_limit_c", self.board_limit_c, 110.0),
        ] {
            if value > maximum {
                bail!("cooling contract {label} relaxes the fixed safety ceiling");
            }
        }
        if self.current_a < 15.0 || self.bridge_loss_w < 40.0 || self.ambient_c < 40.0 {
            bail!("cooling contract must cover the full-current 40 C design point");
        }
        if self.terminal_limit_c < self.ambient_c || self.board_limit_c < self.ambient_c {
            bail!("passive cooling reservoirs cannot be colder than inlet air");
        }
        if self.theta_sink_air_failed_fan_c_per_w < self.theta_sink_air_c_per_w {
            bail!("failed-fan sink-to-air resistance cannot be better than normal cooling");
        }
        // This profile assesses the reviewed assembly in bridge-cooling.md.
        // A substitution requires a reviewed profile, not relabeling evidence.
        if self.heatsink_id != "395-1AB"
            || self.fan_id != "MF80251V1-1000U-G99"
            || self.fan_quantity != 2
        {
            bail!("unsupported cooling assembly: v1 requires 395-1AB and two MF80251V1-1000U-G99 fans");
        }
        let heat = budget(self);
        if ![
            heat.sink_c,
            heat.case_c,
            heat.junction_c,
            heat.failed_fan_sink_c,
            heat.failed_fan_case_c,
            heat.failed_fan_junction_c,
        ]
        .into_iter()
        .all(f64::is_finite)
        {
            bail!("cooling heat budget overflowed");
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct HeatBudget {
    pub ambient_c: f64,
    pub bridge_loss_w: f64,
    pub sink_c: f64,
    pub case_c: f64,
    pub junction_c: f64,
    pub failed_fan_sink_c: f64,
    pub failed_fan_case_c: f64,
    pub failed_fan_junction_c: f64,
    pub design_junction_margin_c: f64,
    pub failed_fan_junction_margin_c: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct NetTemperature {
    pub design_fine_c: f64,
    pub weak_contact_fine_c: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CoolingAssessment {
    pub schema: String,
    pub status: String,
    pub board_sha256: String,
    pub contract_sha256: String,
    pub inner_assessment_sha256: String,
    pub heatsink_id: String,
    pub fan_id: String,
    pub budget: HeatBudget,
    pub per_net: BTreeMap<String, NetTemperature>,
    pub design_budget_compliant: bool,
    pub design_fine_compliant: bool,
    pub failed_fan_budget_compliant: bool,
    pub fan_quantity: u32,
    pub limitations: Vec<String>,
}

fn profile(
    contract: &CoolingContract,
) -> (Vec<neck_run::Scenario>, Vec<neck_run::ConvergencePair>) {
    let params = neck_physics::Params {
        current_a: contract.current_a,
        ambient_k: contract.ambient_c + 273.15,
        terminal_k: contract.terminal_limit_c + 273.15,
        board_k: contract.board_limit_c + 273.15,
        convection_w_m2k: 2.0,
        terminal_conductance_w_k: contract.terminal_conductance_w_per_k,
        board_conductance_w_k: contract.board_conductance_w_per_k,
        conductivity_s_m: 5.5e7,
        alpha_per_k: 0.00393,
        copper_k_w_mk: 350.0,
        fr4_k_w_mk: 0.25,
    };
    let scenario = |name: &str, mesh_mm: f64, params| neck_run::Scenario {
        name: name.into(),
        thickness_um: 63.0,
        mesh_mm,
        params,
    };
    let mut weak = params;
    weak.terminal_conductance_w_k /= 4.0;
    weak.board_conductance_w_k /= 4.0;
    (
        vec![
            scenario("design-coarse", 0.4, params),
            scenario("design-medium", 0.2, params),
            scenario("design-fine", 0.15, params),
            scenario("weak-contact-medium", 0.2, weak),
            scenario("weak-contact-fine", 0.15, weak),
        ],
        vec![
            neck_run::ConvergencePair {
                coarse: "design-coarse".into(),
                fine: "design-medium".into(),
                max_delta_k: 1.0,
            },
            neck_run::ConvergencePair {
                coarse: "design-medium".into(),
                fine: "design-fine".into(),
                max_delta_k: 0.5,
            },
            neck_run::ConvergencePair {
                coarse: "weak-contact-medium".into(),
                fine: "weak-contact-fine".into(),
                max_delta_k: 1.0,
            },
        ],
    )
}

fn budget(contract: &CoolingContract) -> HeatBudget {
    let sink = contract.ambient_c + contract.bridge_loss_w * contract.theta_sink_air_c_per_w;
    let case_c = sink + contract.bridge_loss_w * contract.theta_case_sink_c_per_w;
    let junction = case_c + contract.bridge_loss_w * contract.theta_junction_case_c_per_w;
    let failed_sink =
        contract.ambient_c + contract.bridge_loss_w * contract.theta_sink_air_failed_fan_c_per_w;
    let failed_case = failed_sink + contract.bridge_loss_w * contract.theta_case_sink_c_per_w;
    let failed_junction =
        failed_case + contract.bridge_loss_w * contract.theta_junction_case_c_per_w;
    HeatBudget {
        ambient_c: contract.ambient_c,
        bridge_loss_w: contract.bridge_loss_w,
        sink_c: sink,
        case_c,
        junction_c: junction,
        failed_fan_sink_c: failed_sink,
        failed_fan_case_c: failed_case,
        failed_fan_junction_c: failed_junction,
        design_junction_margin_c: contract.junction_limit_c - junction,
        failed_fan_junction_margin_c: contract.junction_limit_c - failed_junction,
    }
}

fn build_assessment(
    contract: &CoolingContract,
    contract_sha256: String,
    inner: &neck_run::Assessment,
    inner_sha256: String,
) -> Result<CoolingAssessment> {
    let mut per_net = BTreeMap::new();
    for net in ["minus", "ac1", "ac2", "plus"] {
        let design = inner
            .cases
            .iter()
            .find(|case| case.net == net && case.scenario.name == "design-fine")
            .with_context(|| format!("missing design-fine case for {net}"))?;
        let weak = inner
            .cases
            .iter()
            .find(|case| case.net == net && case.scenario.name == "weak-contact-fine")
            .with_context(|| format!("missing weak-contact-fine case for {net}"))?;
        per_net.insert(
            net.into(),
            NetTemperature {
                design_fine_c: design.measurement.max_temperature_k - 273.15,
                weak_contact_fine_c: weak.measurement.max_temperature_k - 273.15,
            },
        );
    }
    let b = budget(contract);
    let design_budget_compliant = b.junction_c <= contract.junction_limit_c;
    let design_fine_compliant = inner
        .cases
        .iter()
        .filter(|case| case.scenario.name == "design-fine")
        .count()
        == 4
        && inner
            .cases
            .iter()
            .filter(|case| case.scenario.name == "design-fine")
            .all(|case| case.measurement.max_temperature_k - 273.15 <= contract.pcb_limit_c);
    let failed_fan_budget_compliant = b.failed_fan_junction_c <= contract.junction_limit_c;
    Ok(CoolingAssessment {
        schema: ASSESSMENT_SCHEMA.into(),
        status: QUALIFICATION_STATUS.into(),
        board_sha256: contract.board_sha256.clone(),
        contract_sha256,
        inner_assessment_sha256: inner_sha256,
        heatsink_id: contract.heatsink_id.clone(),
        fan_id: contract.fan_id.clone(),
        fan_quantity: contract.fan_quantity,
        budget: b,
        per_net,
        design_budget_compliant,
        design_fine_compliant,
        failed_fan_budget_compliant,
        limitations: vec![
            "Cooling conductances and thermal resistances are design requirements, not measured or datasheet-bounded assembly data.".into(),
            "The failed-fan result is a stress calculation and is never an acceptance path.".into(),
            "Numerical model evidence does not qualify bridge package, solder, airflow, or allowable temperatures.".into(),
        ],
    })
}

fn read_contract(path: &Path, board_sha256: &str) -> Result<(Vec<u8>, CoolingContract, String)> {
    let bytes =
        fs::read(path).with_context(|| format!("read cooling contract {}", path.display()))?;
    let (contract, hash) = read_contract_bytes(&bytes, board_sha256)?;
    Ok((bytes, contract, hash))
}

fn validate_paths(paths: &[&Path]) -> Result<()> {
    if paths.iter().any(|path| !path.is_absolute()) {
        bail!("cooling run paths must be absolute");
    }
    Ok(())
}

pub fn run(
    board: &Path,
    native: &Path,
    manufacturing: &Path,
    contract_path: &Path,
    out: &Path,
    tools: &neck_run::Tools,
) -> Result<CoolingAssessment> {
    validate_paths(&[
        board,
        native,
        manufacturing,
        contract_path,
        out,
        &tools.gmsh,
        &tools.grid,
        &tools.solver,
    ])?;
    if out.exists() {
        bail!("refusing existing cooling output directory");
    }
    let board_sha256 = sha256_file(board)?;
    let (contract_bytes, contract, contract_sha256) = read_contract(contract_path, &board_sha256)?;
    let (expected, convergence) = profile(&contract);
    fs::create_dir(out)?;
    fs::write(out.join("contract.json"), &contract_bytes)?;
    let inner_root = out.join("neck-run");
    let inner = neck_run::run_with_scenarios(
        board,
        native,
        manufacturing,
        &inner_root,
        tools,
        &expected,
        &convergence,
    )?;
    let inner_sha256 = sha256_file(&inner_root.join("assessment.json"))?;
    let assessment = build_assessment(&contract, contract_sha256, &inner, inner_sha256)?;
    fs::write(
        out.join("assessment.json"),
        serde_json::to_vec_pretty(&assessment)?,
    )?;
    Ok(assessment)
}

pub fn replay(root: &Path, board: &[u8], expected_contract: &[u8]) -> Result<CoolingAssessment> {
    for path in [
        root.to_owned(),
        root.join("contract.json"),
        root.join("assessment.json"),
        root.join("neck-run"),
    ] {
        if fs::symlink_metadata(&path)?.file_type().is_symlink() {
            bail!("cooling evidence cannot contain symlink aliases");
        }
    }
    let board_sha256 = format!("{:x}", Sha256::digest(board));
    let retained_contract = fs::read(root.join("contract.json"))?;
    if retained_contract != expected_contract {
        bail!("cooling contract differs from the requested source bytes");
    }
    let (contract, contract_sha256) = read_contract_bytes(expected_contract, &board_sha256)?;
    let retained: CoolingAssessment =
        serde_json::from_slice(&fs::read(root.join("assessment.json"))?)?;
    if retained.schema != ASSESSMENT_SCHEMA
        || retained.status != QUALIFICATION_STATUS
        || retained.contract_sha256 != contract_sha256
        || retained.board_sha256 != board_sha256
    {
        bail!("cooling assessment identity or status is invalid");
    }
    let (expected, convergence) = profile(&contract);
    let inner_root = root.join("neck-run");
    let inner = neck_run::replay_with_scenarios(&inner_root, board, &expected, &convergence)?;
    if inner.cases.len() != 20 {
        bail!("cooling inner assessment must contain exactly 20 cases");
    }
    let inner_sha256 = sha256_file(&inner_root.join("assessment.json"))?;
    if retained.inner_assessment_sha256 != inner_sha256 {
        bail!("cooling inner assessment hash mismatch");
    }
    let rebuilt = build_assessment(&contract, contract_sha256, &inner, inner_sha256)?;
    if rebuilt != retained {
        bail!("cooling summary disagrees with retained contract or raw evidence");
    }
    Ok(retained)
}

fn read_contract_bytes(bytes: &[u8], board_sha256: &str) -> Result<(CoolingContract, String)> {
    let contract: CoolingContract =
        serde_json::from_slice(bytes).context("parse cooling contract")?;
    contract.validate(board_sha256)?;
    Ok((contract, format!("{:x}", Sha256::digest(bytes))))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn design_budget_arithmetic_is_explicit() {
        let contract = CoolingContract::for_board("a".repeat(64));
        let b = budget(&contract);
        assert_eq!(b.sink_c, 60.0);
        assert_eq!(b.case_c, 70.0);
        assert_eq!(b.junction_c, 120.0);
        assert_eq!(b.failed_fan_sink_c, 90.0);
        assert_eq!(b.failed_fan_junction_c, 150.0);
        assert!(b.design_junction_margin_c > 0.0);
        assert!(b.failed_fan_junction_margin_c < 0.0);
    }

    #[test]
    fn contract_rejects_nan_and_relaxed_limits() {
        let board = "a".repeat(64);
        let mut contract = CoolingContract::for_board(board.clone());
        contract.bridge_loss_w = f64::NAN;
        assert!(contract.validate(&board).is_err());
        let mut relaxed = CoolingContract::for_board(board.clone());
        relaxed.junction_limit_c = 125.1;
        assert!(relaxed.validate(&board).is_err());
        let mut wrong = CoolingContract::for_board(board.clone());
        wrong.theta_sink_air_c_per_w = 0.0;
        assert!(wrong.validate(&board).is_err());
        let mut overflow = CoolingContract::for_board(board.clone());
        overflow.bridge_loss_w = f64::MAX;
        assert!(overflow.validate(&board).is_err());
        for terminal in [true, false] {
            let mut refrigerated = CoolingContract::for_board(board.clone());
            if terminal {
                refrigerated.terminal_limit_c = refrigerated.ambient_c - 1.0;
            } else {
                refrigerated.board_limit_c = refrigerated.ambient_c - 1.0;
            }
            assert!(refrigerated.validate(&board).is_err());
        }
    }

    #[test]
    fn cooling_profile_has_three_design_meshes_and_declared_pairs() {
        let contract = CoolingContract::for_board("a".repeat(64));
        let (scenarios, pairs) = profile(&contract);
        assert_eq!(scenarios.len(), 5);
        assert_eq!(pairs.len(), 3);
        assert_eq!(scenarios[0].mesh_mm, 0.4);
        assert_eq!(scenarios[2].mesh_mm, 0.15);
        assert!(pairs.iter().all(|pair| pair.max_delta_k <= 1.0));

        let sif = neck_physics::sif(&scenarios[0].params, [1.0, 1.0, 1.0]).unwrap();
        assert!(sif.contains("External Temperature = 368.150000000000"));
        assert!(sif.contains("External Temperature = 353.150000000000"));
    }

    #[test]
    fn contract_rejects_unreviewed_parts_status_and_load_or_parser_changes() {
        let base = CoolingContract::for_board("a".repeat(64));
        assert!(base.validate(&base.board_sha256).is_ok());
        for (key, value) in [
            ("fan_id", serde_json::json!("scrap")),
            ("heatsink_id", serde_json::json!("scrap")),
            ("fan_quantity", serde_json::json!(1)),
            ("qualification", serde_json::json!("qualified")),
            ("current_a", serde_json::json!(14.0)),
            ("bridge_loss_w", serde_json::json!(39.0)),
            ("theta_sink_air_failed_fan_c_per_w", serde_json::json!(0.1)),
            ("unexpected_acceptance", serde_json::json!(true)),
        ] {
            let mut input = serde_json::to_value(&base).unwrap();
            input[key] = value;
            assert!(
                read_contract_bytes(&serde_json::to_vec(&input).unwrap(), &base.board_sha256)
                    .is_err(),
                "accepted {key}"
            );
        }
    }

    #[test]
    fn pcb_peak_is_checked_against_its_own_limit_not_reservoir_or_junction() {
        let mut inner: neck_run::Assessment = serde_json::from_str(include_str!(
            "../../../thermal/evidence/bridge-necks-2026-09-14/assessment.json"
        ))
        .unwrap();
        inner.cases.retain(|c| {
            matches!(
                c.scenario.name.as_str(),
                "nominal-fine" | "hot-weak-cooling-fine"
            )
        });
        for case in &mut inner.cases {
            case.scenario.name = if case.scenario.name == "nominal-fine" {
                "design-fine"
            } else {
                "weak-contact-fine"
            }
            .into();
            case.measurement.max_temperature_k = 109.0 + 273.15;
            // Heat crossing a Robin contact may raise the surface above its
            // reservoir. Those two temperatures are not interchangeable.
            case.measurement.boundary_mean_temperature_k =
                [96.0 + 273.15, 81.0 + 273.15, 90.0 + 273.15];
        }
        let mut contract = CoolingContract::for_board(inner.board_sha256.clone());
        contract.junction_limit_c = 100.0;
        let report =
            build_assessment(&contract, "contract".into(), &inner, "inner".into()).unwrap();
        assert!(report.design_fine_compliant);
        assert!(!report.design_budget_compliant);
        inner
            .cases
            .iter_mut()
            .find(|c| c.scenario.name == "design-fine")
            .unwrap()
            .measurement
            .max_temperature_k = 111.0 + 273.15;
        assert!(
            !build_assessment(&contract, "contract".into(), &inner, "inner".into())
                .unwrap()
                .design_fine_compliant
        );
    }
}
