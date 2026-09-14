//! Source-bound local bridge-neck experiments. Numerical validity is distinct
//! from qualification of the unknown bridge cooling and assembly conditions.
use crate::{
    hash_tree, neck_geometry as geometry, neck_physics as physics, run_process, sha256_file,
    version,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

#[derive(Clone, Debug)]
pub struct Tools {
    pub gmsh: PathBuf,
    pub grid: PathBuf,
    pub solver: PathBuf,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Scenario {
    pub name: String,
    pub thickness_um: f64,
    pub mesh_mm: f64,
    pub params: physics::Params,
}

/// Sampled sensitivities, not a continuous worst-case certificate. The thermal
/// reservoirs are explicit assumptions pending a complete assembly model.
pub fn scenarios() -> Vec<Scenario> {
    let base = physics::Params {
        current_a: 15.0,
        ambient_k: 313.15,
        terminal_k: 353.15,
        board_k: 333.15,
        convection_w_m2k: 8.0,
        terminal_conductance_w_k: 0.02,
        board_conductance_w_k: 0.007,
        conductivity_s_m: 5.8e7,
        alpha_per_k: 0.00393,
        copper_k_w_mk: 400.0,
        fr4_k_w_mk: 0.3,
    };
    let make = |name: &str, thickness_um, mesh_mm, params| Scenario {
        name: name.into(),
        thickness_um,
        mesh_mm,
        params,
    };
    let mut cases = vec![
        make("nominal-coarse", 70.0, 0.4, base),
        make("nominal-medium", 70.0, 0.2, base),
        make("nominal-fine", 70.0, 0.15, base),
        make("thin-copper", 63.0, 0.2, base),
        make("thick-copper", 77.0, 0.2, base),
    ];
    let mut hot = base;
    hot.ambient_k = 333.15;
    hot.terminal_k = 398.15;
    hot.board_k = 373.15;
    cases.push(make("hot-reservoirs", 70.0, 0.2, hot));
    let mut weak = hot;
    weak.convection_w_m2k = 2.0;
    weak.board_conductance_w_k = 0.001;
    weak.terminal_conductance_w_k = 0.002;
    weak.conductivity_s_m = 5.5e7;
    weak.copper_k_w_mk = 350.0;
    weak.fr4_k_w_mk = 0.25;
    cases.push(make("hot-weak-cooling", 63.0, 0.2, weak));
    cases.push(make("hot-weak-cooling-fine", 63.0, 0.15, weak));
    let mut airflow = base;
    airflow.convection_w_m2k = 25.0;
    cases.push(make("increased-airflow", 70.0, 0.2, airflow));
    let mut low = base;
    low.current_a = 5.0;
    cases.push(make("low-current", 70.0, 0.2, low));
    cases
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Case {
    pub net: String,
    pub scenario: Scenario,
    pub measurement: physics::Measurement,
    pub nodes: usize,
    pub areas_m2: [f64; 3],
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Assessment {
    pub schema: String,
    pub status: String,
    pub board_sha256: String,
    pub cases: Vec<Case>,
    pub artifacts: BTreeMap<String, String>,
    pub backend_hashes: BTreeMap<String, String>,
    pub backend_versions: Vec<String>,
    pub limitations: Vec<String>,
}

fn read_model(root: &Path) -> Result<geometry::NeckModel> {
    let native = fs::read(root.join("native.json"))?;
    let binding = zapote_drc::native_binding::validate(std::str::from_utf8(&native)?);
    if binding.status != zapote_core::Status::Pass {
        bail!(
            "thermal native extraction differs from saved board: {:?}",
            binding.findings
        );
    }
    let geometry_binding =
        zapote_drc::native_binding::validate_bridge_neck_geometry(std::str::from_utf8(&native)?);
    if geometry_binding.status != zapote_core::Status::Pass {
        bail!(
            "thermal pad/stackup binding failed: {:?}",
            geometry_binding.findings
        );
    }
    let manufacturing = fs::read(root.join("manufacturing.json"))?;
    let model = geometry::build_neck_model(&native, &manufacturing)?;
    if sha256_file(&root.join("board.kicad_pcb"))? != model.board_sha256 {
        bail!("thermal saved-board identity mismatch");
    }
    Ok(model)
}

fn read_cases(
    root: &Path,
    model: &geometry::NeckModel,
    backends: &BTreeMap<String, String>,
) -> Result<Vec<Case>> {
    let mut cases = Vec::new();
    for neck in &model.necks {
        for scenario in scenarios() {
            let dir = root.join(format!("{}--{}", neck.net, scenario.name));
            verify_commands(&dir, backends)?;
            let expected_geo =
                crate::neck_geo::generate(neck, scenario.thickness_um, scenario.mesh_mm)?;
            if fs::read(dir.join("neck.geo"))? != expected_geo.as_bytes() {
                bail!(
                    "thermal geometry differs from native-derived model: {}",
                    dir.display()
                );
            }
            let mesh = geometry::verify_mesh(
                &fs::read_to_string(dir.join("neck.msh"))?,
                neck,
                scenario.thickness_um,
            )?;
            crate::neck_transfer::verify(
                &fs::read_to_string(dir.join("neck.msh"))?,
                &dir.join("neck"),
            )?;
            let expected_sif = physics::sif(&scenario.params, mesh.areas_m2)?;
            if fs::read(dir.join("case.sif"))? != expected_sif.as_bytes() {
                bail!(
                    "thermal solver input differs from required scenario: {}",
                    dir.display()
                );
            }
            let measurement = physics::parse_validate(
                &fs::read(dir.join("solver.log"))?,
                &fs::read(dir.join("scalars.dat"))?,
                &fs::read(dir.join("scalars.dat.names"))?,
                &scenario.params,
                mesh.areas_m2,
            )?;
            cases.push(Case {
                net: neck.net.clone(),
                scenario,
                measurement,
                nodes: mesh.nodes,
                areas_m2: mesh.areas_m2,
            });
        }
    }
    validate_convergence(&cases)?;
    Ok(cases)
}

fn verify_commands(dir: &Path, backends: &BTreeMap<String, String>) -> Result<()> {
    for (name, program, args) in [
        (
            "gmsh",
            "gmsh",
            vec![
                "neck.geo", "-3", "-format", "msh2", "-o", "neck.msh", "-nt", "1",
            ],
        ),
        ("grid", "ElmerGrid", vec!["14", "2", "neck.msh"]),
        ("solver", "ElmerSolver", vec!["case.sif"]),
    ] {
        let receipt: serde_json::Value =
            serde_json::from_slice(&fs::read(dir.join(format!("{name}.command.json")))?)?;
        let executable = Path::new(
            receipt["program"]
                .as_str()
                .context("missing command program")?,
        );
        let cwd = Path::new(receipt["cwd"].as_str().context("missing command cwd")?);
        let hash = backends
            .get(executable.to_str().context("non-UTF8 backend path")?)
            .context("command program lacks recorded backend identity")?;
        if hash.len() != 64 || !hash.bytes().all(|b| b.is_ascii_hexdigit()) {
            bail!("invalid recorded backend hash");
        }
        if !executable.is_absolute()
            || executable.file_name().and_then(|p| p.to_str()) != Some(program)
            || !cwd.is_absolute()
            || cwd.file_name() != dir.file_name()
            || receipt["args"] != serde_json::json!(args)
            || receipt["environment"]
                != serde_json::json!({"OMP_NUM_THREADS":"1","OMPI_MCA_btl":"self"})
            || receipt["unset_environment"] != serde_json::json!(["ELMER_HOME", "ELMER_LIB"])
            || receipt["timeout_ms"] != serde_json::json!(300000)
        {
            bail!("thermal command receipt differs from required invocation: {name}");
        }
        let expected = format!(
            "{}\n--- stderr ---\n{}",
            fs::read_to_string(dir.join(format!("{name}.stdout")))?,
            fs::read_to_string(dir.join(format!("{name}.stderr")))?
        );
        if fs::read_to_string(dir.join(format!("{name}.log")))? != expected {
            bail!("thermal {name} log differs from retained process output");
        }
    }
    Ok(())
}

/// Numerical tolerances are fixed before examining the PCB results. They are
/// discretization checks, not allowed operating-temperature limits.
fn validate_convergence(cases: &[Case]) -> Result<()> {
    for net in ["minus", "ac1", "ac2", "plus"] {
        let get = |name: &str| -> Result<&Case> {
            cases
                .iter()
                .find(|c| c.net == net && c.scenario.name == name)
                .with_context(|| format!("missing convergence case {net}/{name}"))
        };
        let coarse = get("nominal-coarse")?;
        let medium = get("nominal-medium")?;
        let fine = get("nominal-fine")?;
        if !(coarse.nodes < medium.nodes && medium.nodes < fine.nodes) {
            bail!("mesh refinement did not increase node population: {net}");
        }
        for (a, b, temperature_tolerance_k) in [
            (coarse, medium, 1.0),
            (medium, fine, 0.5),
            (get("hot-weak-cooling")?, get("hot-weak-cooling-fine")?, 1.0),
        ] {
            let delta_t = (a.measurement.max_temperature_k - b.measurement.max_temperature_k).abs();
            let delta_p = (a.measurement.joule_power_w / b.measurement.joule_power_w - 1.0).abs();
            if delta_t > temperature_tolerance_k || delta_p > 0.01 || a.nodes >= b.nodes {
                bail!("thermal mesh convergence failed for {net}/{}: {delta_t} K, power fraction {delta_p}",a.scenario.name);
            }
        }
    }
    Ok(())
}

fn inventory(root: &Path) -> Result<BTreeMap<String, String>> {
    fn no_links(dir: &Path) -> Result<()> {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            if entry.file_type()?.is_symlink() {
                bail!("thermal evidence cannot contain symlinks");
            }
            if entry.file_type()?.is_dir() {
                no_links(&entry.path())?;
            }
        }
        Ok(())
    }
    no_links(root)?;
    let mut hashes = BTreeMap::new();
    hash_tree(root, &mut hashes)?;
    hashes
        .into_iter()
        .filter(|(p, _)| !p.ends_with("/assessment.json"))
        .map(|(p, h)| {
            let rel = Path::new(&p)
                .strip_prefix(root)?
                .to_str()
                .context("non-UTF8 evidence path")?
                .to_owned();
            Ok((rel, h))
        })
        .collect()
}

pub fn run(
    board: &Path,
    native: &Path,
    manufacturing: &Path,
    out: &Path,
    tools: &Tools,
) -> Result<Assessment> {
    for p in [
        board,
        native,
        manufacturing,
        out,
        &tools.gmsh,
        &tools.grid,
        &tools.solver,
    ] {
        if !p.is_absolute() {
            bail!("thermal run paths must be absolute");
        }
    }
    if out.exists() {
        bail!("refusing existing thermal output directory");
    }
    fs::create_dir(out)?;
    let result = run_new(board, native, manufacturing, out, tools);
    if let Err(error) = &result {
        fs::write(
            out.join("failure.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "status":"failed", "error":format!("{error:#}"), "artifacts":inventory(out).ok()
            }))?,
        )?;
    }
    result
}

fn run_new(
    board: &Path,
    native: &Path,
    manufacturing: &Path,
    out: &Path,
    tools: &Tools,
) -> Result<Assessment> {
    fs::copy(board, out.join("board.kicad_pcb"))?;
    fs::copy(native, out.join("native.json"))?;
    fs::copy(manufacturing, out.join("manufacturing.json"))?;
    let model = read_model(out)?;
    let timeout = Duration::from_secs(300);
    let mut backend_hashes = BTreeMap::new();
    for p in [
        &tools.gmsh,
        &tools.grid,
        &tools.solver,
        &std::env::current_exe()?,
    ] {
        hash_tree(p, &mut backend_hashes)?;
    }
    let prefix = tools
        .solver
        .parent()
        .and_then(Path::parent)
        .context("solver must be prefix/bin/ElmerSolver")?;
    for dir in ["lib/elmersolver", "share/elmersolver/lib"] {
        hash_tree(&prefix.join(dir), &mut backend_hashes)?;
    }
    let mut versions = Vec::new();
    for (name, tool, no_args) in [
        ("gmsh", &tools.gmsh, false),
        ("grid", &tools.grid, true),
        ("solver", &tools.solver, false),
    ] {
        versions.push(version(
            tool,
            no_args,
            out,
            &out.join(format!("{name}-version.log")),
            timeout,
        )?);
    }
    run_process(
        Path::new("/usr/bin/git"),
        &["rev-parse", "HEAD"],
        Path::new(env!("CARGO_MANIFEST_DIR")),
        &out.join("git-revision.log"),
        timeout,
    )?;
    run_process(
        Path::new("/usr/bin/git"),
        &["status", "--porcelain"],
        Path::new(env!("CARGO_MANIFEST_DIR")),
        &out.join("git-status.log"),
        timeout,
    )?;
    for neck in &model.necks {
        for scenario in scenarios() {
            let dir = out.join(format!("{}--{}", neck.net, scenario.name));
            fs::create_dir(&dir)?;
            fs::write(
                dir.join("neck.geo"),
                crate::neck_geo::generate(neck, scenario.thickness_um, scenario.mesh_mm)?,
            )?;
            run_process(
                &tools.gmsh,
                &[
                    "neck.geo", "-3", "-format", "msh2", "-o", "neck.msh", "-nt", "1",
                ],
                &dir,
                &dir.join("gmsh.log"),
                timeout,
            )?;
            let mesh = geometry::verify_mesh(
                &fs::read_to_string(dir.join("neck.msh"))?,
                neck,
                scenario.thickness_um,
            )?;
            fs::write(
                dir.join("case.sif"),
                physics::sif(&scenario.params, mesh.areas_m2)?,
            )?;
            run_process(
                &tools.grid,
                &["14", "2", "neck.msh"],
                &dir,
                &dir.join("grid.log"),
                timeout,
            )?;
            crate::neck_transfer::verify(
                &fs::read_to_string(dir.join("neck.msh"))?,
                &dir.join("neck"),
            )?;
            run_process(
                &tools.solver,
                &["case.sif"],
                &dir,
                &dir.join("solver.log"),
                timeout,
            )?;
            physics::parse_validate(
                &fs::read(dir.join("solver.log"))?,
                &fs::read(dir.join("scalars.dat"))?,
                &fs::read(dir.join("scalars.dat.names"))?,
                &scenario.params,
                mesh.areas_m2,
            )?;
            // Intermediate nonlinear iterations are not separate experiments.
            // Keep the final field for inspection and the full iteration log.
            let mut fields = fs::read_dir(dir.join("neck"))?
                .map(|entry| entry.map(|e| e.path()))
                .collect::<std::io::Result<Vec<_>>>()?;
            fields.retain(|p| p.extension().is_some_and(|e| e == "vtu"));
            fields.sort();
            fields.pop();
            for path in fields {
                fs::remove_file(path)?;
            }
            eprintln!("thermal case complete: {} {}", neck.net, scenario.name);
        }
    }
    let cases = read_cases(out, &model, &backend_hashes)?;
    for (path, expected) in &backend_hashes {
        if sha256_file(Path::new(path))? != *expected {
            bail!("thermal backend changed during execution: {path}");
        }
    }
    let report=Assessment {
        schema:"zapote.bridge-neck.assessment.v1".into(), status:"conditional_assessment".into(),
        board_sha256:model.board_sha256, cases, artifacts:inventory(out)?, backend_hashes,
        backend_versions:versions,
        limitations:vec![
            "Sampled local steady-state model; no continuous worst-case or hardware qualification.".into(),
            "Bridge terminal and rest-of-board temperatures/conductances are assumed reservoirs, not validated assembly cooling.".into(),
            "No plated barrel, solder fillet, opposite-side copper or bridge package solid is resolved; hole-wall boundary represents their combined contact.".into(),
            "No allowable copper/assembly temperature contract is established. Existing IPC screen findings remain unchanged.".into(),
        ],
    };
    fs::write(
        out.join("assessment.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(report)
}

/// Re-run the mathematical and semantic checks against retained raw evidence.
/// Report hashes alone cannot authorize changed geometry or scenario inputs.
pub fn replay(root: &Path, board: &[u8]) -> Result<Assessment> {
    let report: Assessment = serde_json::from_slice(&fs::read(root.join("assessment.json"))?)?;
    if report.schema != "zapote.bridge-neck.assessment.v1"
        || report.status != "conditional_assessment"
    {
        bail!("unsupported thermal assessment contract");
    }
    let model = read_model(root)?;
    if fs::read(root.join("board.kicad_pcb"))? != board || report.board_sha256 != model.board_sha256
    {
        bail!("thermal assessment belongs to different saved board");
    }
    if inventory(root)? != report.artifacts {
        bail!("thermal evidence hash mismatch");
    }
    let cases = read_cases(root, &model, &report.backend_hashes)?;
    if serde_json::to_value(&cases)? != serde_json::to_value(&report.cases)? {
        bail!("thermal summary disagrees with raw measurements");
    }
    Ok(report)
}

#[cfg(test)]
mod replay_tests {
    use super::*;
    fn clone_tree(source: &Path, target: &Path) -> Result<()> {
        fs::create_dir(target)?;
        for entry in fs::read_dir(source)? {
            let entry = entry?;
            let out = target.join(entry.file_name());
            if entry.file_type()?.is_dir() {
                clone_tree(&entry.path(), &out)?;
            } else if fs::hard_link(entry.path(), &out).is_err() {
                fs::copy(entry.path(), out)?;
            }
        }
        Ok(())
    }
    // Replace the directory entry, never write through a fixture hard link.
    fn replace(path: &Path, bytes: &[u8]) {
        let temporary = path.with_extension("replacement");
        fs::write(&temporary, bytes).unwrap();
        fs::rename(temporary, path).unwrap();
    }
    #[test]
    fn retained_pcb_replay_rejects_rehashed_model_and_result_mutations() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../thermal/evidence/bridge-necks-2026-09-14");
        let board = fs::read(source.join("board.kicad_pcb")).unwrap();
        let baseline = replay(&source, &board).unwrap();
        assert_eq!(baseline.cases.len(), 40);
        assert!(replay(&source, b"stale board").is_err());
        let temp = std::env::temp_dir().join(format!("zapote-neck-replay-{}", std::process::id()));
        clone_tree(&source, &temp).unwrap();
        let case = "minus--nominal-coarse";
        for mutation in [
            "sif",
            "raw-power",
            "native",
            "command",
            "missing-command",
            "missing-case",
        ] {
            let mut report: Assessment =
                serde_json::from_slice(&fs::read(source.join("assessment.json")).unwrap()).unwrap();
            let relative = match mutation {
                "sif" => format!("{case}/case.sif"),
                "raw-power" => format!("{case}/scalars.dat"),
                "native" => "native.json".into(),
                "command" | "missing-command" => format!("{case}/solver.command.json"),
                _ => format!("{case}/solver.log"),
            };
            let original = fs::read(source.join(&relative)).unwrap();
            match mutation {
                "sif" => {
                    let s = String::from_utf8(original.clone()).unwrap();
                    let changed = s.replace(
                        "External Temperature = 353.150000000000",
                        "External Temperature = 373.150000000000",
                    );
                    assert_ne!(s, changed);
                    replace(&temp.join(&relative), changed.as_bytes());
                }
                "raw-power" => {
                    let mut values: Vec<f64> = std::str::from_utf8(&original)
                        .unwrap()
                        .split_whitespace()
                        .map(|v| v.parse().unwrap())
                        .collect();
                    values[11] *= 1.1;
                    report.cases[0].measurement.joule_power_w = values[11];
                    let changed = values
                        .iter()
                        .map(|v| format!("{v:.12e}"))
                        .collect::<Vec<_>>()
                        .join(" ");
                    replace(&temp.join(&relative), changed.as_bytes());
                }
                "native" => {
                    let mut native: serde_json::Value = serde_json::from_slice(&original).unwrap();
                    native["traces"][0]["width_mm"] = serde_json::json!(100.0);
                    replace(&temp.join(&relative), &serde_json::to_vec(&native).unwrap());
                }
                "command" => {
                    let mut command: serde_json::Value = serde_json::from_slice(&original).unwrap();
                    command["args"] = serde_json::json!(["different.sif"]);
                    replace(
                        &temp.join(&relative),
                        &serde_json::to_vec(&command).unwrap(),
                    );
                }
                _ => fs::remove_file(temp.join(&relative)).unwrap(),
            }
            // An attacker/bug refreshing the manifest must not make the
            // changed electrical/thermal model authoritative.
            report.artifacts = inventory(&temp).unwrap();
            replace(
                &temp.join("assessment.json"),
                &serde_json::to_vec(&report).unwrap(),
            );
            assert!(
                replay(&temp, &board).is_err(),
                "{mutation} falsely accepted"
            );
            replace(&temp.join(&relative), &original);
        }
        fs::remove_dir_all(temp).unwrap();
    }
}
