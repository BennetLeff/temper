//! Harness binding for the power-entry bridge-neck thermal evidence.
//!
//! The thermal solver validates a retained numerical experiment. It does not
//! establish an allowable package, copper, or enclosure temperature: those
//! are assembly and rating inputs that remain explicitly indeterminate here.

use sha2::Digest;
use std::{collections::BTreeSet, path::Path};

use zapote_core::{CheckReport, Finding};

use crate::pfc_power::Report as PfcReport;

const NUMERICAL_RULE: &str = "THERMAL.POWER_ENTRY.BRIDGE_NECK_NUMERICAL";
const APPLICABILITY_RULE: &str = "THERMAL.POWER_ENTRY.BRIDGE_NECK_APPLICABILITY";
pub const RULES: [&str; 2] = [NUMERICAL_RULE, APPLICABILITY_RULE];
pub const COOLING_RULES: [&str; 3] = [
    "THERMAL.POWER_ENTRY.BRIDGE_COOLING_BUDGET",
    "THERMAL.POWER_ENTRY.BRIDGE_COOLING_PCB_TARGET",
    "THERMAL.POWER_ENTRY.BRIDGE_COOLING_CONTACT_SENSITIVITY",
];
pub const PHYSICAL_RULES: [&str; 3] = [
    "THERMAL.POWER_ENTRY.BRIDGE_PHYSICAL_MODEL_NUMERICAL",
    "THERMAL.POWER_ENTRY.BRIDGE_LOSS_BINDING",
    "THERMAL.POWER_ENTRY.BRIDGE_PHYSICAL_APPLICABILITY",
];
pub const JOINT_RULES: [&str; 2] = [
    "THERMAL.POWER_ENTRY.BRIDGE_JOINT_FEM_NUMERICAL",
    "THERMAL.POWER_ENTRY.BRIDGE_JOINT_FEM_APPLICABILITY",
];

#[derive(Debug, Clone)]
pub struct GbjReports {
    pub thermal: CheckReport,
    pub physical: CheckReport,
    pub joint: CheckReport,
}

pub fn run_joint_model(
    root: Option<&Path>,
    native: &[u8],
    manufacturing: Option<&[u8]>,
    pfc: Option<&PfcReport>,
) -> CheckReport {
    let checked = JOINT_RULES.map(str::to_owned).to_vec();
    let result = (|| -> anyhow::Result<_> {
        let root = root.ok_or_else(|| anyhow::anyhow!("joint FEM evidence unavailable"))?;
        let manufacturing = manufacturing
            .ok_or_else(|| anyhow::anyhow!("fresh manufacturing geometry unavailable"))?;
        let waveform = physical_waveform_for_native(
            pfc.ok_or_else(|| anyhow::anyhow!("production PFC waveform unavailable"))?,
            native,
            manufacturing,
        )?;
        zapote_thermal::joint_model::replay(root, native, manufacturing, &waveform)
    })();
    let numerical=match result {
        Ok(a)=>Finding::pass(JOINT_RULES[0],format!("four native joint domains and one shared {:.1} W package source replayed; mesh deltas {:.4}/{:.4} K, wider-domain delta {:.4} K; each contact and global heat balance checked",a.package_allowance_w,a.nominal_mesh_delta_k[0],a.nominal_mesh_delta_k[1],a.domain_delta_k),"power-entry.bridge-joint-fem"),
        Err(e)=>Finding::fail(JOINT_RULES[0],format!("joint FEM replay failed: {e:#}"),"power-entry.bridge-joint-fem"),
    };
    CheckReport::from_findings(vec![numerical,Finding::indeterminate(JOINT_RULES[1],
        "package paths, installed lead/solder geometry, material properties and cooling remain uncertain; tested sensitivities are not a guaranteed bound; no current-screen finding is waived",
        "power-entry.bridge-joint-fem")],checked,vec![])
}

const NETS: [&str; 4] = ["minus", "ac1", "ac2", "plus"];

/// The GBJ package uses the resolved four-diode model for the same mandatory
/// thermal obligations; it cannot consume the GBU-only historical contracts.
pub fn run_gbj_model(
    root: Option<&Path>,
    native: &[u8],
    manufacturing: Option<&[u8]>,
    pfc: Option<&PfcReport>,
) -> GbjReports {
    let result = (|| -> anyhow::Result<_> {
        let root = root.ok_or_else(|| anyhow::anyhow!("GBJ joint evidence unavailable"))?;
        let manufacturing =
            manufacturing.ok_or_else(|| anyhow::anyhow!("manufacturing evidence unavailable"))?;
        let model = zapote_thermal::joint_model::native_model(native, manufacturing)?;
        anyhow::ensure!(
            model.bridge_mpn == "GBJ2510-F",
            "GBJ evidence cannot qualify another package"
        );
        let waveform = physical_waveform_for_native(
            pfc.ok_or_else(|| anyhow::anyhow!("PFC waveform unavailable"))?,
            native,
            manufacturing,
        )?;
        let a = zapote_thermal::joint_model::replay(root, native, manufacturing, &waveform)?;
        anyhow::ensure!(
            a.gbj_diode_power_w.is_some() && a.gbj_cooling_budget.is_some(),
            "GBJ package/cooling evidence missing"
        );
        let named = |name| -> anyhow::Result<_> {
            let mut cases = a.cases.iter().filter(|c| c.scenario.name == name);
            let case = cases
                .next()
                .ok_or_else(|| anyhow::anyhow!("missing GBJ case {name}"))?;
            anyhow::ensure!(cases.next().is_none(), "duplicate GBJ case {name}");
            Ok(case.clone())
        };
        let nominal = named("nominal-fine")?;
        let weak = named("weak-assembly")?;
        let fan_loss = named("fan-loss")?;
        let fan_diode_c = fan_loss
            .gbj_nodes
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("fan-loss diode nodes missing"))?
            .junction_k
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max)
            - 273.15;
        anyhow::ensure!(fan_diode_c.is_finite(), "non-finite fan-loss diode peak");
        let budget = a
            .gbj_cooling_budget
            .ok_or_else(|| anyhow::anyhow!("GBJ cooling budget missing"))?;
        Ok((nominal, weak, fan_loss, fan_diode_c, budget))
    })();
    let object = "power-entry.gbj-thermal";
    let report = |rules: &[&str], findings| {
        CheckReport::from_findings(
            findings,
            rules.iter().map(|r| r.to_string()).collect(),
            vec![],
        )
    };
    let thermal_rules = [
        RULES[0],
        RULES[1],
        COOLING_RULES[0],
        COOLING_RULES[1],
        COOLING_RULES[2],
    ];
    let (nominal, weak, fan_loss, fan_diode_c, budget) = match result {
        Ok(a) => a,
        Err(e) => {
            let failed = |rules: &[&str]| {
                report(
                    rules,
                    rules
                        .iter()
                        .map(|r| {
                            Finding::fail(r, format!("GBJ bound replay failed: {e:#}"), object)
                        })
                        .collect(),
                )
            };
            return GbjReports {
                thermal: failed(&thermal_rules),
                physical: failed(&PHYSICAL_RULES),
                joint: failed(&JOINT_RULES),
            };
        }
    };
    let pass = |r: &str, m: &str| Finding::pass(r, m, object);
    let uncertain = |r: &str, m: &str| Finding::indeterminate(r, m, object);
    let peak = |c: &zapote_thermal::joint_model::Case| {
        c.joint_peaks_k
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max)
            - 273.15
    };
    let budget_finding = if nominal.package_temperature_k - 273.15 <= 110.0
        && budget.conditional_sink_c <= budget.nominal_fem_sink_c
    {
        pass(COOLING_RULES[0],"conditional nominal junction has15 K design margin and the source-bound100 CFM catalog calculation fits the60 C FEM reservoir; installed airflow remains unverified")
    } else {
        Finding::fail(
            COOLING_RULES[0],
            "conditional nominal cooling misses the junction margin or prescribed sink budget",
            object,
        )
    };
    let pcb = if peak(&nominal) <= 110.0 {
        pass(COOLING_RULES[1],"nominal whole-joint peak is below110 C, a conservative upper bound for modeled PCB solids; installed boundaries remain conditional")
    } else {
        uncertain(COOLING_RULES[1],"nominal whole-joint peak exceeds110 C; distinguish copper/FR4 peak from lead/solder before a PCB verdict")
    };
    let weak_finding = if peak(&weak) <= 110.0 && weak.package_temperature_k - 273.15 <= 125.0 {
        pass(COOLING_RULES[2], "tested weak-assembly case stays below the modeled joint/junction limits; this sampled sensitivity is not a guaranteed uncertainty bound")
    } else {
        uncertain(COOLING_RULES[2], "weak-assembly case crosses a joint or junction limit; assembly applicability remains unresolved")
    };
    let fan_message = format!("fan-loss sensitivity reaches {fan_diode_c:.2} C hottest diode and {:.2} C whole-joint peak; conditional diode limit 125 C; shutdown behavior and installed airflow remain unmodeled", peak(&fan_loss));
    let fan_finding = if fan_diode_c > 125.0 {
        Finding::fail(
            COOLING_RULES[2],
            fan_message,
            "power-entry.gbj-thermal.fan-loss",
        )
    } else {
        Finding::indeterminate(
            COOLING_RULES[2],
            fan_message,
            "power-entry.gbj-thermal.fan-loss",
        )
    };
    GbjReports {
        thermal: report(&thermal_rules,vec![pass(RULES[0],"four native joints replay with independent geometry, energy and mesh checks"),uncertain(RULES[1],"installed cooling, assembly paths, AC2 current distribution and fan-loss transient remain unresolved"),budget_finding,pcb,weak_finding,fan_finding]),
        physical: report(&PHYSICAL_RULES,vec![pass(PHYSICAL_RULES[0],"four diode nodes, shared case and FEM ports close every nodal and global balance"),pass(PHYSICAL_RULES[1],"exact GBJ datasheet and production waveform bind the one40 W allocation; VF remains a point estimate"),uncertain(PHYSICAL_RULES[2],"mutual die paths, lead material and actual hot losses remain uncertain")]),
        joint: report(&JOINT_RULES,vec![pass(JOINT_RULES[0],"source-bound GBJ raw FEM replay passed; physical trace side preserved"),uncertain(JOINT_RULES[1],"numerical validity does not qualify assembly cooling or resolve area-current distribution")]),
    }
}

pub fn physical_waveform(
    pfc: &PfcReport,
) -> anyhow::Result<zapote_thermal::physical_model::WaveformInput> {
    use sha2::{Digest, Sha256};
    let profile_sha256 = format!("{:x}", Sha256::digest(serde_json::to_vec(&pfc.waveform)?));
    let samples = pfc
        .waveform
        .samples
        .iter()
        .map(|s| zapote_thermal::physical_model::WaveformSample {
            weight: s.weight,
            line_sign: s.line_sign,
            inductor_a: s.inductor_a,
        })
        .collect();
    let mut neck_rms_a = std::collections::BTreeMap::new();
    for net in NETS {
        let current = physical_branch_current(&pfc.branches, net)
            .ok_or_else(|| anyhow::anyhow!("missing determined PFC branch for {net}"))?;
        neck_rms_a.insert(net.to_owned(), current);
    }
    Ok(zapote_thermal::physical_model::WaveformInput {
        profile_sha256,
        samples,
        neck_rms_a,
    })
}

/// Bind branch currents to the exact native terminal traces of the reviewed
/// package. Graph split ordinals may change after copper edits.
pub fn physical_waveform_for_native(
    pfc: &PfcReport,
    native: &[u8],
    manufacturing: &[u8],
) -> anyhow::Result<zapote_thermal::physical_model::WaveformInput> {
    use sha2::{Digest, Sha256};
    let model = zapote_thermal::joint_model::native_model(native, manufacturing)?;
    let neck_rms_a = model
        .necks
        .iter()
        .map(|neck| {
            let current = trace_cut_current(&pfc.branches, &neck.net, &neck.trace_uuid)
                .or_else(|| {
                    (model.bridge_mpn == "GBJ2510-F" && neck.net == "ac2")
                        .then(|| gbj_ac2_assumed_current(pfc, &neck.trace_uuid))
                        .flatten()
                })
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "missing unique determined PFC cut for {} ({})",
                        neck.net,
                        neck.trace_uuid
                    )
                })?;
            Ok((neck.net.clone(), current))
        })
        .collect::<anyhow::Result<_>>()?;
    let waveform = zapote_thermal::physical_model::WaveformInput {
        profile_sha256: format!("{:x}", Sha256::digest(serde_json::to_vec(&pfc.waveform)?)),
        samples: pfc
            .waveform
            .samples
            .iter()
            .map(|s| zapote_thermal::physical_model::WaveformSample {
                weight: s.weight,
                line_sign: s.line_sign,
                inductor_a: s.inductor_a,
            })
            .collect(),
        neck_rms_a,
    };
    waveform.validate()?;
    Ok(waveform)
}

// This exact candidate's AC2 pad-contact graph has no determined cut. Model
// the full terminal RMS as an explicit sensitivity; keep branch-current
// applicability indeterminate. This is not a claim of solved current sharing.
fn gbj_ac2_assumed_current(pfc: &PfcReport, uuid: &str) -> Option<f64> {
    let current = pfc
        .waveform
        .samples
        .iter()
        .map(|s| s.weight * s.inductor_a * s.inductor_a)
        .sum::<f64>()
        .sqrt();
    if !current.is_finite() || current <= 0.0 {
        return None;
    }
    let mut segments = std::collections::BTreeSet::new();
    for b in &pfc.branches {
        let Some((trace, index)) = b.id.split_once(':') else {
            continue;
        };
        if trace != uuid {
            continue;
        }
        let n: usize = index.parse().ok()?;
        if index != n.to_string()
            || b.net != "ac2"
            || b.kind != "trace"
            || b.determined_rms_a.is_some()
            || !b.rms_envelope_a.is_finite()
            || (b.rms_envelope_a - current).abs() > 1e-8 * current
            || !segments.insert(n)
        {
            return None;
        }
    }
    (!segments.is_empty() && segments.iter().copied().eq(0..segments.len())).then_some(current)
}

/// Replay the shared package/lead/barrel/solder model through the production
/// harness boundary. Physical applicability is intentionally indeterminate
/// while package internals or assembly paths are unknown.
#[expect(
    clippy::too_many_arguments,
    reason = "evidence inputs remain explicit at this harness boundary"
)]
pub fn run_with_physical_model(
    _evidence_root: Option<&Path>,
    board: &[u8],
    pfc: Option<&PfcReport>,
    contract: Option<&[u8]>,
    assessment: Option<&[u8]>,
    source_bytes: Option<&[u8]>,
    native_json: Option<&[u8]>,
    manufacturing_json: Option<&[u8]>,
) -> CheckReport {
    let checked = PHYSICAL_RULES.iter().map(|r| (*r).to_owned()).collect();
    let result = (|| -> anyhow::Result<_> {
        let pfc = pfc
            .ok_or_else(|| anyhow::anyhow!("PFC report unavailable for physical-model binding"))?;
        let contract =
            contract.ok_or_else(|| anyhow::anyhow!("physical-model contract unavailable"))?;
        let assessment =
            assessment.ok_or_else(|| anyhow::anyhow!("physical-model assessment unavailable"))?;
        let board_sha256 = format!("{:x}", sha2::Sha256::digest(board));
        let waveform = physical_waveform(pfc)?;
        let parsed: zapote_thermal::physical_model::PhysicalModelContract =
            serde_json::from_slice(contract)?;
        let native = native_json.ok_or_else(|| {
            anyhow::anyhow!("native geometry required for physical-model binding")
        })?;
        let manufacturing = manufacturing_json.ok_or_else(|| {
            anyhow::anyhow!("manufacturing geometry required for physical-model binding")
        })?;
        anyhow::ensure!(
            parsed.geometry_sha256.is_some(),
            "physical-model contract requires native geometry fingerprint"
        );
        let model = zapote_thermal::neck_geometry::build_neck_model_variant(native, manufacturing)?;
        zapote_thermal::physical_model::validate_geometry_binding(&parsed, &model)?;
        let stackup = zapote_thermal::neck_geometry::extract_stackup_dimensions(native)?;
        anyhow::ensure!(
            parsed.paths.iter().all(|p| (p.copper_thickness_um.nominal
                - stackup.copper_thickness_um)
                .abs()
                < 1e-9
                && (p.barrel_length_mm.nominal - stackup.board_thickness_mm).abs() < 1e-9),
            "physical-model copper/barrel dimensions differ from native stackup"
        );
        let fresh = if let Some(source_bytes) = source_bytes {
            zapote_thermal::physical_model::replay_with_source_bytes(
                contract,
                assessment,
                &board_sha256,
                &waveform,
                source_bytes,
            )?
        } else {
            ensure_source_not_claimed_archived(&parsed)?;
            zapote_thermal::physical_model::replay(contract, assessment, &board_sha256, &waveform)?
        };
        Ok(fresh)
    })();
    let mut findings = Vec::new();
    match result {
        Ok(a) => {
            findings.push(Finding::pass(PHYSICAL_RULES[0], format!("coupled lumped package/lead/barrel/solder screening KCL balanced {:.3e} W; package {:.2} C; board {:.2} C; sink flow {:.4} W; board flow {:.4} W; terminal resistance is a separate lumped approximation; resolved joint FEM is checked independently", a.global_power_residual_w, a.package_temperature_c, a.board_temperature_c, a.package_to_sink_w, a.leads_to_board_w), "power-entry.bridge-physical-model"));
            findings.push(if a.source_bytes_verified {
                Finding::pass(
                    PHYSICAL_RULES[1],
                    format!(
                        "GBU2510A diode loss recomputed from the retained PFC waveform and archived source identity: {:.4} W at the fixed 1.0 V / 12.5 A point; curve extrapolation and the 40 W allowance remain unproven",
                        a.diode_loss_w
                    ),
                    "power-entry.bridge-physical-model",
                )
            } else {
                Finding::indeterminate(
                    PHYSICAL_RULES[1],
                    format!(
                        "GBU2510A diode loss recomputed from retained PFC waveform ({:.4} W), but manufacturer source bytes were not supplied for hash verification",
                        a.diode_loss_w
                    ),
                    "power-entry.bridge-physical-model",
                )
            });
            findings.push(Finding::indeterminate(PHYSICAL_RULES[2], "package internals and lead/barrel/solder assembly paths remain unknown; numerical replay cannot establish ratings", "power-entry.bridge-physical-model"));
        }
        Err(error) => {
            findings.push(Finding::fail(
                PHYSICAL_RULES[0],
                format!("physical-model replay failed: {error:#}"),
                "power-entry.bridge-physical-model",
            ));
            findings.push(Finding::fail(
                PHYSICAL_RULES[1],
                "loss binding was not established from the production PFC waveform",
                "power-entry.bridge-physical-model",
            ));
            findings.push(Finding::indeterminate(
                PHYSICAL_RULES[2],
                "physical applicability cannot be assessed without a valid replay",
                "power-entry.bridge-physical-model",
            ));
        }
    }
    CheckReport::from_findings(findings, checked, vec![])
}

fn ensure_source_not_claimed_archived(
    contract: &zapote_thermal::physical_model::PhysicalModelContract,
) -> anyhow::Result<()> {
    anyhow::ensure!(
        contract.loss.source_status != "byte_archived",
        "byte-archived physical-model source requires physical_model_source bytes"
    );
    Ok(())
}

/// Evaluate the selected cooling design without treating unverified assembly
/// targets as measured boundary conditions or waiving the separate IPC screen.
pub fn run_with_contract(
    evidence_root: Option<&Path>,
    board: &[u8],
    pfc: Option<&PfcReport>,
    contract: Option<&[u8]>,
) -> CheckReport {
    let Some(contract_bytes) = contract else {
        return run(evidence_root, board, pfc);
    };
    let checked = RULES
        .into_iter()
        .chain(COOLING_RULES)
        .map(str::to_owned)
        .collect();
    let result = (|| -> anyhow::Result<_> {
        let root = evidence_root.ok_or_else(|| anyhow::anyhow!("cooling evidence missing"))?;
        let assessment = zapote_thermal::bridge_cooling::replay(root, board, contract_bytes)?;
        let contract: zapote_thermal::bridge_cooling::CoolingContract =
            serde_json::from_slice(contract_bytes)?;
        let errors = bind_current_values(
            NETS.into_iter()
                .map(|net| (net, "design-fine", contract.current_a)),
            pfc,
        );
        if !errors.is_empty() {
            anyhow::bail!(errors.join("; "));
        }
        Ok((assessment, contract))
    })();
    let mut findings = Vec::new();
    match result {
        Err(error) => {
            findings.push(Finding::fail(
                NUMERICAL_RULE,
                format!("cooling replay/binding failed: {error:#}"),
                "power-entry.bridge-cooling",
            ));
            for rule in COOLING_RULES {
                findings.push(Finding::indeterminate(
                    rule,
                    "no valid current-bound cooling replay",
                    "power-entry.bridge-cooling",
                ));
            }
        }
        Ok((assessment, contract)) => {
            findings.push(Finding::pass(NUMERICAL_RULE, "cooling contract and raw thermal evidence replayed; four currents bound to exact PFC branches", "power-entry.bridge-cooling"));
            let budget_message = format!(
                "conditional junction {:.2} C, limit {:.2} C; failed-fan stress {:.2} C (shutdown protection remains unverified)",
                assessment.budget.junction_c, contract.junction_limit_c, assessment.budget.failed_fan_junction_c);
            findings.push(if assessment.design_budget_compliant {
                Finding::pass(
                    COOLING_RULES[0],
                    budget_message,
                    "power-entry.bridge-cooling",
                )
            } else {
                Finding::fail(
                    COOLING_RULES[0],
                    budget_message,
                    "power-entry.bridge-cooling",
                )
            });
            let peak = assessment
                .per_net
                .values()
                .map(|v| v.design_fine_c)
                .fold(f64::NEG_INFINITY, f64::max);
            let weak = assessment
                .per_net
                .values()
                .map(|v| v.weak_contact_fine_c)
                .fold(f64::NEG_INFINITY, f64::max);
            let pcb_message = format!(
                "conditional local PCB peak {peak:.2} C against {:.2} C design ceiling",
                contract.pcb_limit_c
            );
            findings.push(if assessment.design_fine_compliant {
                Finding::pass(COOLING_RULES[1], pcb_message, "power-entry.bridge-cooling")
            } else {
                Finding::fail(COOLING_RULES[1], pcb_message, "power-entry.bridge-cooling")
            });
            findings.push(Finding::indeterminate(COOLING_RULES[2],
                format!("quarter-conductance sensitivity peak {weak:.2} C; PCB ceiling {:.2} C; actual lead/solder/rest-board conductances remain unbounded", contract.pcb_limit_c),
                "power-entry.bridge-cooling"));
        }
    }
    findings.push(Finding::indeterminate(APPLICABILITY_RULE,
        "selected cooling parts and temperature targets are design requirements; installed airflow, contact resistance, package-to-lead coupling, ratings and fault protection are not qualified; no current-capacity finding is waived",
        "power-entry.bridge-cooling"));
    CheckReport::from_findings(findings, checked, vec![])
}

/// Run the retained bridge-neck replay and bind its currents to the PFC
/// branch model. Missing evidence is indeterminate; supplied evidence that
/// cannot be replayed or bound fails closed. A successful replay is still
/// conditional because cooling and temperature ratings are unqualified.
pub fn run(evidence_root: Option<&Path>, board: &[u8], pfc: Option<&PfcReport>) -> CheckReport {
    let mut findings = Vec::new();
    let numerical = match evidence_root {
        None => {
            findings.push(Finding::indeterminate(
                NUMERICAL_RULE,
                "bridge-neck thermal evidence directory was not supplied",
                "power-entry.bridge-necks",
            ));
            false
        }
        Some(root) if !root.is_dir() => {
            findings.push(Finding::fail(
                NUMERICAL_RULE,
                format!(
                    "bridge-neck thermal evidence directory is missing: {}",
                    root.display()
                ),
                root.display().to_string(),
            ));
            false
        }
        Some(root) => match zapote_thermal::neck_run::replay(root, board) {
            Err(error) => {
                findings.push(Finding::fail(
                    NUMERICAL_RULE,
                    format!("bridge-neck thermal evidence replay failed: {error:#}"),
                    root.display().to_string(),
                ));
                false
            }
            Ok(assessment) => {
                let mut errors = validate_assessment(&assessment.cases);
                errors.extend(bind_currents(&assessment.cases, pfc));
                if errors.is_empty() {
                    findings.push(Finding::pass(
                        NUMERICAL_RULE,
                        "bridge-neck thermal evidence replayed and currents bound to PFC branches",
                        root.display().to_string(),
                    ));
                    true
                } else {
                    findings.push(Finding::fail(
                        NUMERICAL_RULE,
                        errors.join("; "),
                        root.display().to_string(),
                    ));
                    false
                }
            }
        },
    };

    // This is deliberately emitted for every PowerEntry run, including a
    // numerically valid replay. No package, copper, solder, or enclosure
    // temperature limit is established by the retained model.
    findings.push(Finding::indeterminate(
        APPLICABILITY_RULE,
        if numerical {
            "thermal replay is numerical evidence only; bridge package, solder, rest-board temperatures and cooling are assumed, with no rating contract"
        } else {
            "thermal applicability is unqualified; bridge package, solder, rest-board temperatures and cooling have no rating contract"
        },
        "power-entry.bridge-necks",
    ));

    CheckReport::from_findings(
        findings,
        RULES.iter().map(|rule| (*rule).into()).collect(),
        vec![],
    )
}

fn validate_assessment(cases: &[zapote_thermal::neck_run::Case]) -> Vec<String> {
    let scenario_names: Vec<String> = zapote_thermal::neck_run::scenarios()
        .into_iter()
        .map(|scenario| scenario.name)
        .collect();
    let expected: BTreeSet<_> = NETS
        .iter()
        .flat_map(|net| {
            scenario_names
                .iter()
                .map(move |scenario| ((*net).to_owned(), scenario.clone()))
        })
        .collect();
    let mut seen = BTreeSet::new();
    let mut errors = Vec::new();
    for case in cases {
        if !NETS.contains(&case.net.as_str()) {
            errors.push(format!("unexpected bridge-neck net {}", case.net));
            continue;
        }
        if !scenario_names
            .iter()
            .any(|name| name == &case.scenario.name)
        {
            errors.push(format!(
                "unexpected bridge-neck scenario {} for {}",
                case.scenario.name, case.net
            ));
        }
        if !case.scenario.params.current_a.is_finite() || case.scenario.params.current_a <= 0.0 {
            errors.push(format!(
                "non-positive or non-finite current for {} / {}",
                case.net, case.scenario.name
            ));
        }
        let measurement = &case.measurement;
        if !measurement.resistance_ohm.is_finite()
            || !measurement.joule_power_w.is_finite()
            || !measurement.max_temperature_k.is_finite()
            || measurement.resistance_ohm <= 0.0
            || measurement.joule_power_w < 0.0
        {
            errors.push(format!(
                "invalid thermal measurement for {} / {}",
                case.net, case.scenario.name
            ));
        }
        if !seen.insert((case.net.clone(), case.scenario.name.clone())) {
            errors.push(format!(
                "duplicate thermal case {} / {}",
                case.net, case.scenario.name
            ));
        }
    }
    if seen.len() != expected.len() || seen.iter().any(|key| !expected.contains(key)) {
        errors.push(format!(
            "thermal evidence case population is incomplete: got {}, expected {}",
            seen.len(),
            expected.len()
        ));
    }
    errors
}

fn bind_currents(cases: &[zapote_thermal::neck_run::Case], pfc: Option<&PfcReport>) -> Vec<String> {
    bind_current_values(
        cases.iter().map(|case| {
            (
                case.net.as_str(),
                case.scenario.name.as_str(),
                case.scenario.params.current_a,
            )
        }),
        pfc,
    )
}

fn bind_current_values<'a>(
    currents: impl Iterator<Item = (&'a str, &'a str, f64)>,
    pfc: Option<&PfcReport>,
) -> Vec<String> {
    let Some(pfc) = pfc else {
        return vec!["PFC branch report is unavailable for thermal current binding".into()];
    };
    let mut errors = Vec::new();
    for (net, scenario, current) in currents {
        // The 5 A case is intentional sensitivity evidence. Every nominal,
        // hot, copper, airflow, and full-current case must equal the actual
        // determined branch current from the PFC report.
        let Some(expected) = branch_current(&pfc.branches, net) else {
            errors.push(format!(
                "no determined PFC bridge branch for thermal net {}",
                net
            ));
            continue;
        };
        if !current_matches(scenario, current, expected) {
            errors.push(format!(
                "thermal current {} A for {} / {} does not match determined PFC branch {} A",
                current, net, scenario, expected
            ));
        }
    }
    errors
}

fn current_matches(scenario: &str, current: f64, expected: f64) -> bool {
    if scenario == "low-current" && (current - 5.0).abs() <= 1e-9 {
        return true;
    }
    let tolerance = 1e-6 * expected.abs().max(1.0);
    (current - expected).abs() <= tolerance
}

// Width changes can move graph split points, so segment ordinals are not a
// stable identity. Bind the complete native trace UUID and net, require a
// well-formed contiguous segmentation and one determined positive cut current.
// Uniform current over the pad-overlap portions remains a model assumption.
fn physical_branch_current(branches: &[crate::pfc_power::Branch], net: &str) -> Option<f64> {
    let uuid = match net {
        "minus" => "1a8c9e36-4bbf-486e-a8a9-34985b0b249e",
        "ac1" => "6be299ab-3af0-4444-8bb5-c26c3d6443f6",
        "ac2" => "44d2e757-cc34-46a2-88aa-5ae29db62817",
        "plus" => "e7dc2c72-d7b2-4456-afa6-efe227e0f8f8",
        _ => return None,
    };
    trace_cut_current(branches, net, uuid)
}

fn trace_cut_current(branches: &[crate::pfc_power::Branch], net: &str, uuid: &str) -> Option<f64> {
    let mut segments = std::collections::BTreeMap::new();
    for b in branches {
        let Some((trace, index)) = b.id.split_once(':') else {
            continue;
        };
        if trace != uuid {
            continue;
        }
        let n: usize = index.parse().ok()?;
        if index != n.to_string()
            || b.net != net
            || b.kind != "trace"
            || segments.insert(n, b.determined_rms_a).is_some()
        {
            return None;
        }
    }
    if segments.keys().copied().ne(0..segments.len()) {
        return None;
    }
    let mut determined = segments.values().filter_map(|x| *x);
    let current = determined.next()?;
    if determined.next().is_some() {
        return None;
    }
    (current.is_finite() && current > 0.0).then_some(current)
}

fn branch_current(branches: &[crate::pfc_power::Branch], net: &str) -> Option<f64> {
    // These exact UUID-plus-segment IDs identify the four bridge neck
    // traces in the source/native graph. Keep the net check as a second
    // binding dimension; a net-only match is not sufficient evidence.
    let expected_id = match net {
        "minus" => "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2",
        "ac1" => "6be299ab-3af0-4444-8bb5-c26c3d6443f6:2",
        "ac2" => "44d2e757-cc34-46a2-88aa-5ae29db62817:0",
        "plus" => "e7dc2c72-d7b2-4456-afa6-efe227e0f8f8:2",
        _ => return None,
    };
    let matches: Vec<&crate::pfc_power::Branch> = branches
        .iter()
        .filter(|branch| branch.net == net && branch.id == expected_id)
        .collect();
    if matches.len() != 1 {
        return None;
    }
    let value = matches[0].determined_rms_a?;
    (value.is_finite() && value > 0.0).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn branch(id: &str, net: &str, current: Option<f64>) -> crate::pfc_power::Branch {
        crate::pfc_power::Branch {
            id: id.into(),
            net: net.into(),
            kind: "trace".into(),
            width_mm: 2.5,
            determined_rms_a: current,
            rms_envelope_a: current.unwrap_or(0.0),
            sampled_peak_envelope_a: current.unwrap_or(0.0),
            nominal_external_capacity_a: None,
        }
    }

    #[test]
    fn physical_current_tracks_width_dependent_segmentation_without_uuid_fallback() {
        let uuid = "6be299ab-3af0-4444-8bb5-c26c3d6443f6";
        for n in [1, 2] {
            let mut b: Vec<_> = (0..=n)
                .map(|i| branch(&format!("{uuid}:{i}"), "ac1", None))
                .collect();
            b[n].determined_rms_a = Some(15.0);
            assert_eq!(physical_branch_current(&b, "ac1"), Some(15.0));
            b[0].determined_rms_a = Some(14.0);
            assert_eq!(physical_branch_current(&b, "ac1"), None);
        }
        for id in [
            format!("{uuid}:20000"),
            format!("X{uuid}:0"),
            format!("{uuid}:00"),
        ] {
            assert_eq!(
                physical_branch_current(&[branch(&id, "ac1", Some(15.0))], "ac1"),
                None
            );
        }
    }

    #[test]
    fn missing_evidence_is_indeterminate_and_rules_are_checked() {
        let report = run(None, b"board", None);
        assert_eq!(report.status, zapote_core::Status::Indeterminate);
        assert_eq!(report.checked_rules, RULES.map(str::to_owned));
        assert!(report
            .findings
            .iter()
            .any(|finding| finding.rule == NUMERICAL_RULE));
        assert!(report
            .findings
            .iter()
            .any(|finding| finding.rule == APPLICABILITY_RULE));
    }

    #[test]
    fn configured_missing_evidence_is_a_failure() {
        let report = run(
            Some(Path::new("/nonexistent/zapote-thermal-evidence")),
            b"board",
            None,
        );
        assert_eq!(report.status, zapote_core::Status::Fail);
    }

    #[test]
    fn configured_cooling_contract_cannot_pass_without_replay() {
        let report = run_with_contract(None, b"board", None, Some(b"{}"));
        assert_eq!(report.status, zapote_core::Status::Fail);
        assert_eq!(
            report.checked_rules.len(),
            RULES.len() + COOLING_RULES.len()
        );
        assert!(report.findings.iter().any(
            |f| f.rule == APPLICABILITY_RULE && f.status == zapote_core::Status::Indeterminate
        ));
        assert!(!report
            .findings
            .iter()
            .any(|f| f.status == zapote_core::Status::Pass));
    }

    #[test]
    fn missing_uuid_does_not_fall_back_to_net_only() {
        let branches = vec![branch("unrelated:2", "minus", Some(15.0))];
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn segment_id_collision_cannot_supply_or_override_current() {
        let id = "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2";
        let collision = format!("{id}0000");
        let mut branches = vec![branch(&collision, "minus", Some(14.0))];
        assert_eq!(branch_current(&branches, "minus"), None);
        branches.push(branch(id, "minus", Some(15.0)));
        assert_eq!(branch_current(&branches, "minus"), Some(15.0));
        branches.push(branch(id, "minus", Some(15.0)));
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn undetermined_matching_segment_fails_closed() {
        let id = "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2";
        let branches = vec![branch(id, "minus", None)];
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn disagreeing_matching_segments_are_not_collapsed() {
        let id = "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2";
        let branches = vec![
            branch(id, "minus", Some(15.0)),
            branch(id, "minus", Some(14.0)),
        ];
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn nominal_wrong_current_is_rejected_but_low_sensitivity_is_allowed() {
        assert!(!current_matches("nominal-medium", 14.0, 15.0));
        assert!(current_matches("low-current", 5.0, 15.0));
    }
}
