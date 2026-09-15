//! Four native joint domains coupled to one shared, uncertain package node.
//! FEM supplies conductor heating and terminal heat flow. The package's
//! inaccessible internal paths remain explicit assumptions, not ratings.
use crate::{
    gbj_package,
    joint_fem::{self, JointInput, RunConfig, RunReport},
    neck_geometry,
    neck_run::Tools,
    physical_model::{self, WaveformInput},
};
use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

const SCHEMA: &str = "zapote.bridge-joint-package.v1";
const POWER_W: f64 = 40.0;
const SINK_K: f64 = 333.15;
const BOARD_K: f64 = 353.15;
const MAX_ITERATIONS: usize = 10;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Scenario {
    pub name: String,
    pub mesh_m: f64,
    pub domain_scale: f64,
    pub weak_assembly: bool,
}

/// Predeclared comparisons; the weak corner is a sensitivity, not a proven
/// worst-case bound over unknown package construction or airflow.
pub fn profile() -> Vec<Scenario> {
    [
        ("nominal-coarse", 0.0006, 1.0, false),
        ("nominal-medium", 0.0003, 1.0, false),
        ("nominal-fine", 0.00015, 1.0, false),
        ("wider-domain", 0.0003, 1.5, false),
        ("weak-assembly", 0.0003, 1.0, true),
    ]
    .into_iter()
    .map(|(name, mesh_m, domain_scale, weak_assembly)| Scenario {
        name: name.into(),
        mesh_m,
        domain_scale,
        weak_assembly,
    })
    .collect()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Case {
    pub scenario: Scenario,
    pub iterations: usize,
    pub package_temperature_k: f64,
    pub lead_temperatures_k: [f64; 4],
    pub joint_peaks_k: [f64; 4],
    pub conductor_power_w: [f64; 4],
    pub lead_port_outward_w: [f64; 4],
    pub package_to_sink_w: f64,
    pub joints_to_board_w: f64,
    pub global_residual_w: f64,
    pub contact_residual_w: [f64; 4],
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gbj_nodes: Option<gbj_package::Nodes>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gbj_junction_residual_w: Option<[f64; 4]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gbj_case_residual_w: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Assessment {
    pub schema: String,
    pub applicability: String,
    pub input_hashes: BTreeMap<String, String>,
    pub geometry_sha256: String,
    pub waveform_sha256: String,
    pub fixed_vf_loss_estimate_w: f64,
    pub package_allowance_w: f64,
    pub cases: Vec<Case>,
    pub nominal_mesh_delta_k: [f64; 2],
    pub domain_delta_k: f64,
    pub limitations: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gbj_diode_power_w: Option<[f64; 4]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gbj_cooling_budget: Option<crate::gbj_cooling::Budget>,
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

/// Select a reviewed package from the actual saved native component identity.
/// Each translator checks pin semantics and geometry against the board bytes.
pub fn native_model(native: &[u8], manufacturing: &[u8]) -> Result<neck_geometry::NeckModel> {
    ensure!(
        zapote_drc::native_binding::validate(std::str::from_utf8(native)?).status
            == zapote_core::Status::Pass,
        "joint native geometry differs from saved board bytes"
    );
    let value: serde_json::Value = serde_json::from_slice(native)?;
    let bridges = value["components"]
        .as_array()
        .context("missing components")?
        .iter()
        .filter(|c| c["id"] == "bridge")
        .collect::<Vec<_>>();
    ensure!(bridges.len() == 1, "expected one native bridge");
    match bridges[0]["mpn"].as_str() {
        Some("GBU2510A") => neck_geometry::build_neck_model_variant(native, manufacturing),
        Some("GBJ2510-F") => neck_geometry::build_gbj_neck_model(native, manufacturing),
        _ => anyhow::bail!("unreviewed bridge thermal identity"),
    }
}

/// Allocate the one total allowance using the production waveform's two
/// conducting diode pairs. Constant VF estimates are not hot-loss bounds.
pub fn gbj_diode_power(waveform: &WaveformInput) -> Result<[f64; 4]> {
    waveform.validate()?;
    let mut weight = [0.0; 4];
    for s in &waveform.samples {
        ensure!(
            s.line_sign.abs() == 1.0,
            "diode allocation requires signed half-cycles"
        );
        let pair = if s.line_sign > 0.0 { [0, 3] } else { [1, 2] };
        for diode in pair {
            weight[diode] += s.weight * s.inductor_a;
        }
    }
    let total: f64 = weight.iter().sum();
    ensure!(
        total.is_finite() && total > 0.0,
        "missing diode loss waveform"
    );
    Ok(weight.map(|w| POWER_W * w / total))
}

/// The package/lead coupling has a closed-form Newton step when conductor
/// Joule heat is held at the last FEM iteration. A fresh FEM solve must then
/// satisfy every contact balance before this step can become a result.
pub fn coupling_step(
    old: [f64; 4],
    outward: [f64; 4],
    g: [f64; 4],
    sink_g: f64,
    contact_g: f64,
) -> Result<(f64, [f64; 4])> {
    ensure!(
        sink_g.is_finite() && sink_g > 0.0 && contact_g.is_finite() && contact_g > 0.0,
        "invalid package conductance"
    );
    ensure!(
        old.iter().chain(outward.iter()).all(|x| x.is_finite())
            && g.iter().all(|x| x.is_finite() && *x > 0.0),
        "invalid local response"
    );
    let numerator = POWER_W
        + sink_g * SINK_K
        + (0..4)
            .map(|i| contact_g * (outward[i] + g[i] * old[i]) / (contact_g + g[i]))
            .sum::<f64>();
    let denominator = sink_g
        + (0..4)
            .map(|i| contact_g * g[i] / (contact_g + g[i]))
            .sum::<f64>();
    let package = numerator / denominator;
    let leads = std::array::from_fn(|i| {
        (contact_g * package + outward[i] + g[i] * old[i]) / (contact_g + g[i])
    });
    ensure!(
        package.is_finite() && leads.iter().all(|v| v.is_finite()),
        "nonfinite coupled temperatures"
    );
    Ok((package, leads))
}

fn inputs(
    native: &[u8],
    model: &neck_geometry::NeckModel,
    waveform: &WaveformInput,
    s: &Scenario,
) -> Result<Vec<JointInput>> {
    waveform.validate()?;
    let gbj = model.bridge_mpn == "GBJ2510-F";
    let value: serde_json::Value = serde_json::from_slice(native)?;
    let board = value["board_file_utf8"]
        .as_str()
        .context("missing native board")?;
    let dims = zapote_drc::stackup::physical_dimensions(board).map_err(anyhow::Error::msg)?;
    let stack = neck_geometry::extract_stackup_dimensions(native)?;
    let core = *dims
        .layers_mm
        .get("dielectric 1")
        .context("two-layer joint requires dielectric 1")?;
    ensure!(
        dims.layers_mm
            .keys()
            .filter(|k| k.starts_with("dielectric "))
            .count()
            == 1,
        "joint requires one dielectric core"
    );
    model
        .necks
        .iter()
        .map(|neck| {
            let mut i = JointInput::default();
            i.pad_shape = match neck.pad_shape {
                1 => joint_fem::PadShape::Rectangle,
                2 if neck.pad_size_mm[0] == neck.pad_size_mm[1] => joint_fem::PadShape::Round,
                2 => joint_fem::PadShape::VerticalObround,
                _ => anyhow::bail!("unsupported native pad"),
            };
            i.pad_width_m = neck.pad_size_mm[0] * 1e-3;
            i.pad_length_m = neck.pad_size_mm[1] * 1e-3;
            i.solder_width_m = i.pad_width_m;
            i.solder_length_m = i.pad_length_m;
            i.drill_diameter_m = neck.drill_mm * 1e-3;
            i.trace_width_m = neck.trace_width_mm * 1e-3;
            i.trace_length_m = neck.trace_length_mm * 1e-3;
            if gbj {
                i.trace_on_back = neck.trace_layer == "B.Cu";
            }
            i.copper_thickness_m = stack.copper_thickness_um * 1e-6;
            i.board_thickness_m = core * 1e-3;
            // Yangjie S-B407 rev2.5 p3: I=1.02..1.27 mm, M=.46...56 mm.
            i.lead_width_m = if gbj { 0.001 } else { 0.001145 };
            i.lead_length_m = if gbj { 0.0007 } else { 0.00051 };
            i.lead_top_z_m = 0.003; // Installed standoff is an assembly assumption.
            i.package_temperature_k = 373.15;
            i.board_temperature_k = BOARD_K;
            i.current_a = *waveform
                .neck_rms_a
                .get(&neck.net)
                .context("missing native branch RMS")?;
            i.substrate_half_width_m *= s.domain_scale;
            i.substrate_back_margin_m *= s.domain_scale;
            if s.weak_assembly {
                i.copper_thickness_m *= 0.9;
                i.barrel_plating_m *= 0.5;
                i.lead_width_m = if gbj { 0.0009 } else { 0.00102 };
                i.lead_length_m = if gbj { 0.0006 } else { 0.00046 };
                i.lead_top_z_m = 0.006;
                i.materials.lead_sigma_s_m *= 0.5;
                i.materials.lead_k_w_mk *= 0.5;
                i.solder_thickness_m *= 0.5;
            }
            i.validate()?;
            Ok(i)
        })
        .collect()
}

fn local(
    input: JointInput,
    path: PathBuf,
    mesh: f64,
    tools: &Tools,
    replay: bool,
) -> Result<RunReport> {
    let report = if replay {
        joint_fem::replay(&path)?
    } else {
        joint_fem::run_at_mesh(
            &RunConfig {
                input: input.clone(),
                output_dir: path,
                gmsh: tools.gmsh.clone(),
                elmergrid: tools.grid.clone(),
                elmersolver: tools.solver.clone(),
                timeout: Duration::from_secs(300),
            },
            mesh,
        )?
    };
    ensure!(
        report.input == input && report.cases.len() == 1 && report.cases[0].mesh_size_m == mesh,
        "retained local solve differs from required native/assembly/load input"
    );
    Ok(report)
}

fn batch(
    input: Vec<JointInput>,
    root: &Path,
    mesh: f64,
    tools: &Tools,
    replay: bool,
) -> Result<Vec<RunReport>> {
    // Each solver has its own immutable output directory and one CPU thread.
    std::thread::scope(|scope| {
        let jobs = input
            .into_iter()
            .enumerate()
            .map(|(n, input)| {
                let dir = root.join(format!("lead-{n}"));
                scope.spawn(move || local(input, dir, mesh, tools, replay))
            })
            .collect::<Vec<_>>();
        jobs.into_iter()
            .map(|j| {
                j.join()
                    .map_err(|_| anyhow::anyhow!("local FEM worker panicked"))?
            })
            .collect()
    })
}

fn case(
    native: &[u8],
    model: &neck_geometry::NeckModel,
    waveform: &WaveformInput,
    s: &Scenario,
    root: &Path,
    tools: &Tools,
    replay: bool,
) -> Result<Case> {
    let base = inputs(native, model, waveform, s)?;
    ensure!(base.len() == 4, "four bridge joints required");
    let basis = base
        .iter()
        .cloned()
        .map(|mut i| {
            i.current_a = 0.0;
            i.package_temperature_k = BOARD_K + 1.0;
            i
        })
        .collect();
    let basis = batch(basis, &root.join("thermal-basis"), s.mesh_m, tools, replay)?;
    // Lead port flux is isolated from the two board ports' shared edge nodes.
    let g: [f64; 4] = std::array::from_fn(|n| basis[n].cases[0].measurement.flux_w[0]);
    ensure!(
        g.iter().all(|v| v.is_finite() && *v > 0.0),
        "zero-current thermal basis is not passive"
    );
    let sink_g = if s.weak_assembly { 0.5 } else { 1.0 };
    let contact_g = if s.weak_assembly { 0.1 } else { 0.2 };
    let mut package = SINK_K + POWER_W / sink_g;
    let mut lead = [package; 4];
    let diode_power = if model.bridge_mpn == "GBJ2510-F" {
        Some(gbj_diode_power(waveform)?)
    } else {
        None
    };
    let sink_k = if s.name == "fan-loss" { 373.15 } else { SINK_K };
    let mut gbj_nodes = diode_power
        .map(|p| gbj_package::solve_at_sink([BOARD_K; 4], [0.0; 4], g, p, s.weak_assembly, sink_k))
        .transpose()?;
    if let Some(nodes) = &gbj_nodes {
        package = nodes
            .junction_k
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        lead = nodes.lead_k;
    }
    for iteration in 0..MAX_ITERATIONS {
        let requested = base
            .iter()
            .cloned()
            .enumerate()
            .map(|(n, mut i)| {
                i.package_temperature_k = lead[n];
                i
            })
            .collect();
        let solved = batch(
            requested,
            &root.join(format!("iteration-{iteration}")),
            s.mesh_m,
            tools,
            replay,
        )?;
        let m: Vec<_> = solved.iter().map(|r| &r.cases[0].measurement).collect();
        let outward = std::array::from_fn(|n| -m[n].flux_w[0]);
        let gbj_balance = gbj_nodes
            .as_ref()
            .zip(diode_power)
            .map(|(nodes, p)| {
                gbj_package::balances_at_sink(nodes, outward, p, s.weak_assembly, sink_k)
            })
            .transpose()?;
        let contact = gbj_balance.as_ref().map_or_else(
            || std::array::from_fn(|n| contact_g * (lead[n] - package) - outward[n]),
            |b| b.lead_residual_w,
        );
        let sink = gbj_balance
            .as_ref()
            .map_or(sink_g * (package - SINK_K), |b| b.sink_w);
        let board: f64 = m.iter().map(|m| -m.flux_w[1] - m.flux_w[2]).sum();
        let total = POWER_W + m.iter().map(|m| m.joule_w).sum::<f64>();
        let residual = total - sink - board;
        let package_balanced = gbj_balance.as_ref().is_none_or(|b| {
            b.case_residual_w.abs() <= 1e-5 && b.junction_residual_w.iter().all(|v| v.abs() <= 1e-5)
        });
        if contact.iter().all(|v| v.abs() <= 1e-5) && residual.abs() <= 1e-5 && package_balanced {
            return Ok(Case {
                scenario: s.clone(),
                iterations: iteration + 1,
                package_temperature_k: package,
                lead_temperatures_k: lead,
                joint_peaks_k: std::array::from_fn(|n| m[n].max_temperature_k),
                conductor_power_w: std::array::from_fn(|n| m[n].joule_w),
                lead_port_outward_w: outward,
                package_to_sink_w: sink,
                joints_to_board_w: board,
                global_residual_w: residual,
                contact_residual_w: contact,
                gbj_nodes,
                gbj_junction_residual_w: gbj_balance.as_ref().map(|b| b.junction_residual_w),
                gbj_case_residual_w: gbj_balance.as_ref().map(|b| b.case_residual_w),
            });
        }
        if let Some(p) = diode_power {
            let nodes = gbj_package::solve_at_sink(lead, outward, g, p, s.weak_assembly, sink_k)?;
            package = nodes
                .junction_k
                .iter()
                .copied()
                .fold(f64::NEG_INFINITY, f64::max);
            lead = nodes.lead_k;
            gbj_nodes = Some(nodes);
        } else {
            (package, lead) = coupling_step(lead, outward, g, sink_g, contact_g)?;
        }
    }
    anyhow::bail!("package/FEM coupling did not converge within {MAX_ITERATIONS} iterations")
}

fn assess(root: &Path, tools: &Tools, replay: bool) -> Result<Assessment> {
    let native = fs::read(root.join("native.json"))?;
    let manufacturing = fs::read(root.join("manufacturing.json"))?;
    ensure!(
        zapote_drc::native_binding::validate(std::str::from_utf8(&native)?).status
            == zapote_core::Status::Pass,
        "joint native geometry differs from saved board bytes"
    );
    let waveform_bytes = fs::read(root.join("waveform.json"))?;
    let waveform: WaveformInput = serde_json::from_slice(&waveform_bytes)?;
    waveform.validate()?;
    let source = fs::read(root.join("source.pdf"))?;
    let model = native_model(&native, &manufacturing)?;
    let gbj = model.bridge_mpn == "GBJ2510-F";
    ensure!(
        hash(&source)
            == if gbj {
                gbj_package::REVIEWED_SOURCE_SHA256
            } else {
                physical_model::REVIEWED_SOURCE_SHA256
            },
        "unreviewed bridge source bytes"
    );
    let mut scenarios = profile();
    if gbj {
        scenarios.push(Scenario {
            name: "fan-loss".into(),
            mesh_m: 0.0003,
            domain_scale: 1.0,
            weak_assembly: false,
        });
    }
    let cases = scenarios
        .iter()
        .map(|s| {
            case(
                &native,
                &model,
                &waveform,
                s,
                &root.join(&s.name),
                tools,
                replay,
            )
        })
        .collect::<Result<Vec<_>>>()?;
    let delta = |a: &Case, b: &Case| {
        a.joint_peaks_k
            .iter()
            .zip(b.joint_peaks_k)
            .map(|(a, b)| (a - b).abs())
            .fold(
                (a.package_temperature_k - b.package_temperature_k).abs(),
                f64::max,
            )
    };
    let mesh_delta = [delta(&cases[0], &cases[1]), delta(&cases[1], &cases[2])];
    ensure!(
        mesh_delta[0] <= 1.0 && mesh_delta[1] <= 0.5,
        "same-physics mesh temperature convergence failed"
    );
    // Requested mesh sizes alone do not prove refinement actually occurred.
    // Check independent mesh counts and conductor losses as well as peaks.
    for n in 0..4 {
        let mut previous: Option<RunReport> = None;
        for c in &cases[..3] {
            let p = root.join(&c.scenario.name).join(format!(
                "iteration-{}/lead-{n}/report.json",
                c.iterations - 1
            ));
            let r: RunReport = serde_json::from_slice(&fs::read(p)?)?;
            if let Some(before) = previous {
                ensure!(
                    r.cases[0].mesh.nodes > before.cases[0].mesh.nodes
                        && r.cases[0].mesh.tetrahedra > before.cases[0].mesh.tetrahedra,
                    "requested refinement did not increase the native joint mesh"
                );
                let a = before.cases[0].measurement.joule_w;
                let b = r.cases[0].measurement.joule_w;
                ensure!(
                    (a - b).abs() / a.abs().max(b.abs()) <= 0.02,
                    "joint conductor heating has not converged within 2 percent"
                );
            }
            previous = Some(r);
        }
    }
    let domain_delta = delta(&cases[1], &cases[3]);
    let mut hashes = BTreeMap::new();
    for name in [
        "native.json",
        "manufacturing.json",
        "waveform.json",
        "source.pdf",
    ] {
        hashes.insert(name.into(), hash(&fs::read(root.join(name))?));
    }
    let gbj_cooling_budget = if gbj {
        let budget = crate::gbj_cooling::evaluate(root)?;
        for (name, _) in crate::gbj_cooling::SOURCES {
            hashes.insert(name.into(), hash(&fs::read(root.join(name))?));
        }
        Some(budget)
    } else {
        None
    };
    let limitations = if gbj {
        vec![
        "GBJ2510-F DS21221 rev11-2: four diode nodes, each RthetaJC=1 K/W typical to one isothermal case. Weak sensitivity assumes 1.5 K/W per element. Mutual die thermal impedances are not specified.".into(),
        "One 40 W allowance is split across diode pairs using the production waveform; 1.05 V at 12.5 A/25 C is a point estimate, not a guaranteed waveform/hot-loss bound.".into(),
        "Case-to-sink .25 K/W nominal/.5 weak and each diode-to-endpoint-lead .1 W/K nominal/.05 weak are assembly/internal-path assumptions. The electrical pairing is an assumed thermal network, not sourced package construction.".into(),
        "Sourced external lead section is I=.9..1.1 by R=.6...8 mm. Nominal uses1.0x.7 mm; weak uses.9x.6 mm. Lead material, front-side full-pad solder,25um plating and3mm standoff are assumed; weak halves lead conductivities/plating/solder, uses6mm standoff and90% copper.".into(),
        "Actual F.Cu/B.Cu trace side is retained with leads and solder on F.Cu. Sidewalls are adiabatic, board cuts80 C, sink60 C. These are prescribed reservoirs; installed airflow and full-board current/thermal fields are not solved.".into(),
        "Package_temperature_k denotes the hottest lumped GBJ diode node, not a resolved die temperature. Whole-joint peak includes lead/solder; a value above110 C does not by itself prove PCB failure. No screen finding or physical qualification is waived.".into(),
    ]
    } else {
        vec![
            "One 40 W package allowance is an unproven design assumption; the fixed 1 V VF point is not a hot-current loss bound.".into(),
            "Package-to-sink 1 W/K and package-to-lead .2 W/K are uncertain lumped paths; weak sensitivity halves both. Package node is not a resolved die junction.".into(),
            "Lead electrical/thermal material, 3 mm installed standoff, 25 um plating and full-pad solder fill are assembly assumptions. Weak corner uses 6 mm standoff, minimum sourced lead section, half lead conductivities/plating/solder and 90% copper.".into(),
            "Side walls are adiabatic; board cut faces are 80 C and sink is 60 C. Wider-domain sensitivity is reported, not assumed converged.".into(),
            "Joint peak includes lead and solder and is only an upper bound on copper/FR4 peak. Tested sensitivities are not a guaranteed uncertainty envelope; no current finding is waived.".into(),
    ]
    };
    Ok(Assessment {
        schema: SCHEMA.into(),
        applicability: "indeterminate".into(),
        input_hashes: hashes,
        geometry_sha256: neck_geometry::geometry_fingerprint(&model)?,
        waveform_sha256: physical_model::waveform_sha256(&waveform)?,
        fixed_vf_loss_estimate_w: 2.0
            * (if gbj { 1.05 } else { 1.0 })
            * waveform
                .samples
                .iter()
                .map(|s| s.weight * s.inductor_a)
                .sum::<f64>(),
        package_allowance_w: POWER_W,
        cases,
        nominal_mesh_delta_k: mesh_delta,
        domain_delta_k: domain_delta,
        limitations,
        gbj_cooling_budget,
        gbj_diode_power_w: if gbj {
            Some(gbj_diode_power(&waveform)?)
        } else {
            None
        },
    })
}

pub fn run(
    native: &Path,
    manufacturing: &Path,
    waveform: &WaveformInput,
    source: &Path,
    out: &Path,
    tools: &Tools,
) -> Result<Assessment> {
    ensure!(
        out.is_absolute() && !out.exists(),
        "output must be a new absolute directory"
    );
    fs::create_dir_all(out)?;
    if native_model(&fs::read(native)?, &fs::read(manufacturing)?)?.bridge_mpn == "GBJ2510-F" {
        let sources =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../thermal/cooling-options/sources");
        crate::gbj_cooling::evaluate(&sources)?;
        for (name, _) in crate::gbj_cooling::SOURCES {
            fs::copy(sources.join(name), out.join(name))?;
        }
    }
    for (path, name) in [
        (native, "native.json"),
        (manufacturing, "manufacturing.json"),
        (source, "source.pdf"),
    ] {
        fs::copy(path, out.join(name))?;
    }
    fs::write(
        out.join("waveform.json"),
        serde_json::to_vec_pretty(waveform)?,
    )?;
    let report = assess(out, tools, false)?;
    fs::write(
        out.join("assessment.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(report)
}

/// Replay all local raw evidence and the shared package iteration. External
/// board/native/waveform bytes anchor the producer's retained input hashes.
pub fn replay(
    root: &Path,
    native: &[u8],
    manufacturing: &[u8],
    waveform: &WaveformInput,
) -> Result<Assessment> {
    let normalized = |bytes: &[u8]| -> Result<serde_json::Value> {
        let mut value: serde_json::Value = serde_json::from_slice(bytes)?;
        if let Some(object) = value.as_object_mut() {
            object.remove("evidence_binding");
        }
        if let Some(object) = value
            .get_mut("input")
            .and_then(serde_json::Value::as_object_mut)
        {
            object.remove("board_id");
        }
        Ok(value)
    };
    ensure!(
        normalized(&fs::read(root.join("native.json"))?)? == normalized(native)?
            && normalized(&fs::read(root.join("manufacturing.json"))?)?
                == normalized(manufacturing)?,
        "joint model native/manufacturing evidence changed"
    );
    let retained: WaveformInput = serde_json::from_slice(&fs::read(root.join("waveform.json"))?)?;
    ensure!(
        &retained == waveform,
        "joint model waveform differs from production"
    );
    let stored: Assessment = serde_json::from_slice(&fs::read(root.join("assessment.json"))?)?;
    let unused = Tools {
        gmsh: PathBuf::new(),
        grid: PathBuf::new(),
        solver: PathBuf::new(),
    };
    let fresh = assess(root, &unused, true)?;
    ensure!(
        serde_json::to_value(&stored)? == serde_json::to_value(&fresh)?,
        "joint model summary differs from raw replay"
    );
    Ok(fresh)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn package_source_is_allocated_once_and_kcl_matches_independent_reference() {
        // In this independent lumped reference each joint adds .5 W at its
        // contact, with .02 W/K to 80 C. Exact solution is Tp=5920/59 C.
        let (p, t) = coupling_step([373.15; 4], [0.1; 4], [0.02; 4], 1.0, 0.2).unwrap();
        assert!((p - 273.15 - 5920.0 / 59.0).abs() < 1e-10);
        assert!(t.iter().all(|v| (v - 273.15 - 5945.0 / 59.0).abs() < 1e-10));
        assert!(
            ((p - SINK_K) + t.iter().map(|v| 0.02 * (v - BOARD_K)).sum::<f64>() - 42.0).abs()
                < 1e-10
        );
    }
    #[test]
    fn invalid_conductance_cannot_produce_a_temperature() {
        assert!(coupling_step([373.15; 4], [0.1; 4], [0.02; 4], 0.0, 0.2).is_err());
    }
}
