//! Bounded external Gmsh + Elmer reference runner for a constant-material bar.
//!
//! This crate deliberately contains orchestration and acceptance checks only. The
//! finite-element model is supplied by the caller's `bar.geo` and `case.sif`.

use anyhow::{bail, Context, Result};
pub mod bridge_cooling;
pub mod cooker_envelope;
pub mod gbj_cooling;
pub mod gbj_package;
pub mod joint_fem;
pub mod joint_mesh;
pub mod joint_model;
pub mod joint_physics;
mod neck_geo;
pub mod neck_geometry;
pub mod neck_physics;
pub mod neck_run;
pub mod neck_transfer;
pub mod physical_model;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::{Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

pub const MESH_SIZES_M: [f64; 3] = [0.0005, 0.00025, 0.000125];
pub const AMBIENT_K: f64 = 293.15;
pub const EXPECTED_RESISTANCE_OHM: f64 = 0.01 / (58e6 * 0.002 * 0.001);
pub const EXPECTED_POWER_W: f64 = 0.02 * 0.02 / EXPECTED_RESISTANCE_OHM;
pub const EXPECTED_RISE_K: f64 = 58e6 * 0.02 * 0.02 / (8.0 * 400.0);
const REFERENCE_THREADS: &str = "1";

#[derive(Debug, Clone)]
pub struct Config {
    pub gmsh: PathBuf,
    pub elmergrid: PathBuf,
    pub elmersolver: PathBuf,
    pub output_dir: PathBuf,
    pub bar_geo: PathBuf,
    pub case_sif: PathBuf,
    pub timeout: Duration,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Measurement {
    pub resistance_ohm: f64,
    pub power_w: f64,
    pub peak_temperature_k: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaseResult {
    pub mesh_size_m: f64,
    pub measurement: Measurement,
    pub temperature_rise_k: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunReport {
    pub status: String,
    pub cases: Vec<CaseResult>,
    pub source_sha256: String,
    pub omp_num_threads: Option<String>,
    pub source_identity: Option<String>,
    pub dirty: Option<String>,
    pub tool_versions: Vec<String>,
    pub timings_ms: Vec<u128>,
    pub artifact_sha256: BTreeMap<String, String>,
    pub solver_library_sha256: BTreeMap<String, String>,
    pub mesh_node_counts: Vec<usize>,
}

/// Parse the single steady-state result of the pinned bar case. Names, raw
/// log and scalars must agree; repeated or incomplete results fail closed.
pub fn parse_elmer_outputs_named(
    log: &[u8],
    scalars: &[u8],
    names: Option<&[u8]>,
) -> Result<Measurement> {
    let log = std::str::from_utf8(log)?;
    if !log.contains("MAIN: *** Elmer Solver: ALL DONE ***") {
        bail!("missing Elmer completion marker");
    }
    let names = std::str::from_utf8(names.context("scalar names required")?)?;
    let expected = [
        "max: temperature",
        "min: temperature",
        "int mean: temperature",
        "res: total joule heating",
        "res: effective resistance",
    ];
    let mut columns = BTreeMap::new();
    let (_, column_text) = names
        .split_once("Variables in columns of matrix:")
        .context("missing scalar column header")?;
    for line in column_text.lines().filter(|line| !line.trim().is_empty()) {
        let (index, label) = line.split_once(':').context("malformed scalar name row")?;
        let index: usize = index
            .trim()
            .parse()
            .context("invalid scalar column index")?;
        if columns.insert(index, label.trim()).is_some() {
            bail!("duplicate scalar column");
        }
    }
    if columns.len() != expected.len()
        || expected
            .iter()
            .enumerate()
            .any(|(i, label)| columns.get(&(i + 1)) != Some(label))
    {
        bail!("unexpected scalar column names");
    }
    let data = std::str::from_utf8(scalars)?;
    let rows: Vec<_> = data.lines().filter(|s| !s.trim().is_empty()).collect();
    if rows.len() != 1 {
        bail!("expected exactly one scalar row");
    }
    let nums: Vec<f64> = rows[0]
        .split_whitespace()
        .map(str::parse)
        .collect::<std::result::Result<_, _>>()?;
    if nums.len() != expected.len() || nums.iter().any(|v| !v.is_finite()) {
        bail!("expected five finite scalar values");
    }
    let power = unique_log_measure(log, "Total Heating Power")?;
    let resistance = unique_log_measure(log, "Effective Resistance")?;
    for (raw, scalar) in [(power, nums[3]), (resistance, nums[4])] {
        if (raw - scalar).abs() > 1e-10 * raw.abs().max(1e-15) {
            bail!("raw log disagrees with scalar result");
        }
    }
    if (nums[1] - AMBIENT_K).abs() > 1e-6 || nums[2] < nums[1] || nums[2] > nums[0] {
        bail!("temperature extrema/mean contradict bar boundary conditions");
    }
    let measurement = Measurement {
        resistance_ohm: resistance,
        power_w: power,
        peak_temperature_k: nums[0],
    };
    validate_measurement(&measurement)?;
    Ok(measurement)
}

fn unique_log_measure(log: &str, name: &str) -> Result<f64> {
    let mut result = None;
    for line in log.lines() {
        let Some(rest) = line.trim().strip_prefix("StatCurrentSolve:") else {
            continue;
        };
        let Some((label, value)) = rest.split_once(':') else {
            continue;
        };
        if label.trim() != name {
            continue;
        }
        if result.is_some() {
            bail!("duplicate {name}");
        }
        let value: f64 = value.trim().parse()?;
        if !value.is_finite() {
            bail!("nonfinite {name}");
        }
        result = Some(value);
    }
    result.with_context(|| format!("missing {name}"))
}

pub fn validate_measurement(m: &Measurement) -> Result<()> {
    for (name, value) in [
        ("resistance_ohm", m.resistance_ohm),
        ("power_w", m.power_w),
        ("peak_temperature_k", m.peak_temperature_k),
    ] {
        if !value.is_finite() {
            bail!("{name} is non-finite");
        }
    }
    if m.resistance_ohm <= 0.0 || m.power_w < 0.0 || m.peak_temperature_k < 0.0 {
        bail!("measurement contains an invalid negative or zero value")
    }
    Ok(())
}

pub fn validate_measurements(cases: &[CaseResult]) -> Result<()> {
    if cases.len() != MESH_SIZES_M.len() {
        bail!(
            "expected exactly three mesh measurements, got {}",
            cases.len()
        );
    }
    let mut sizes = cases.iter().map(|c| c.mesh_size_m).collect::<Vec<_>>();
    sizes.sort_by(f64::total_cmp);
    if sizes != MESH_SIZES_M.iter().copied().rev().collect::<Vec<_>>() {
        bail!("unexpected mesh sizes");
    }
    for pair in sizes.windows(2) {
        if pair[0] == pair[1] {
            bail!("duplicate mesh measurement");
        }
    }
    for c in cases {
        validate_measurement(&c.measurement)?;
        if !c.temperature_rise_k.is_finite() {
            bail!("temperature rise is non-finite");
        }
        if (c.temperature_rise_k - (c.measurement.peak_temperature_k - AMBIENT_K)).abs() > 1e-12 {
            bail!("temperature rise disagrees with measured peak");
        }
    }
    let mut ordered = cases.to_vec();
    ordered.sort_by(|a, b| a.mesh_size_m.total_cmp(&b.mesh_size_m));
    let a = ordered[0].temperature_rise_k;
    let b = ordered[1].temperature_rise_k;
    if (a - b).abs() / a.abs().max(1e-12) >= 0.005 {
        bail!("finest two temperature rises differ by at least 0.5%");
    }
    for c in cases {
        if (c.measurement.resistance_ohm - EXPECTED_RESISTANCE_OHM).abs() / EXPECTED_RESISTANCE_OHM
            >= 1e-4
        {
            bail!("resistance outside 1e-4 relative tolerance");
        }
        if (c.measurement.power_w - EXPECTED_POWER_W).abs() / EXPECTED_POWER_W >= 1e-4 {
            bail!("power outside 1e-4 relative tolerance");
        }
        if (c.temperature_rise_k - EXPECTED_RISE_K).abs() / EXPECTED_RISE_K >= 0.01 {
            bail!("temperature rise outside 1% relative tolerance");
        }
    }
    Ok(())
}

pub fn sha256_file(path: &Path) -> Result<String> {
    let bytes = fs::read(path).with_context(|| format!("read {}", path.display()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn run_process(
    program: &Path,
    args: &[&str],
    cwd: &Path,
    log: &Path,
    timeout: Duration,
) -> Result<ExitStatus> {
    let started = Instant::now();
    let mut command = Command::new(program);
    command.env("OMPI_MCA_btl", "self");
    command.env("OMP_NUM_THREADS", REFERENCE_THREADS);
    // Do not let an inherited Elmer plugin search override the pinned installation.
    command.env_remove("ELMER_HOME").env_remove("ELMER_LIB");
    command.stdin(Stdio::null());
    #[cfg(unix)]
    command.process_group(0);
    fs::write(
        log.with_extension("command.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "program": program, "args": args, "cwd": cwd,
            "environment": {"OMP_NUM_THREADS": REFERENCE_THREADS, "OMPI_MCA_btl": "self"},
            "unset_environment": ["ELMER_HOME", "ELMER_LIB"], "timeout_ms": timeout.as_millis()
        }))?,
    )?;
    let stdout_path = log.with_extension("stdout");
    let stderr_path = log.with_extension("stderr");
    command.stdout(Stdio::from(fs::File::create(&stdout_path)?));
    command.stderr(Stdio::from(fs::File::create(&stderr_path)?));
    let mut child = command
        .args(args)
        .current_dir(cwd)
        .spawn()
        .with_context(|| format!("launch {}", program.display()))?;
    let status = loop {
        if child.try_wait()?.is_some() {
            break child.wait()?;
        }
        if started.elapsed() > timeout {
            #[cfg(unix)]
            {
                let pid = i32::try_from(child.id())?;
                // SAFETY: process_group(0) created a new group with this child's
                // positive PID. Negating it targets only that group, including
                // descendants that could otherwise keep writing retained output.
                unsafe {
                    libc::kill(-pid, libc::SIGKILL);
                }
            }
            let _ = child.kill();
            let _ = child.wait();
            bail!("{} exceeded timeout {:?}", program.display(), timeout);
        }
        thread::sleep(Duration::from_millis(10));
    };
    let mut text = fs::read_to_string(&stdout_path)?;
    text.push_str("\n--- stderr ---\n");
    text.push_str(&fs::read_to_string(&stderr_path)?);
    fs::write(log, text).with_context(|| format!("write {}", log.display()))?;
    if started.elapsed() > timeout {
        bail!("{} exceeded timeout {:?}", program.display(), timeout);
    }
    if !status.success() {
        bail!("{} failed ({})", program.display(), status);
    }
    Ok(status)
}

fn version(
    program: &Path,
    no_args: bool,
    cwd: &Path,
    log: &Path,
    timeout: Duration,
) -> Result<String> {
    let args: &[&str] = if no_args { &[] } else { &["--version"] };
    run_process(program, args, cwd, log, timeout)?;
    Ok(fs::read_to_string(log)?)
}

fn git_output(config: &Config, args: &[&str], name: &str) -> Result<String> {
    let log = config.output_dir.join(format!("{name}.log"));
    run_process(
        Path::new("/usr/bin/git"),
        args,
        Path::new(env!("CARGO_MANIFEST_DIR")),
        &log,
        config.timeout,
    )?;
    Ok(fs::read_to_string(log.with_extension("stdout"))?
        .trim()
        .to_owned())
}

fn hash_tree(root: &Path, out: &mut BTreeMap<String, String>) -> Result<()> {
    if root.is_file() {
        out.insert(root.display().to_string(), sha256_file(root)?);
        return Ok(());
    }
    for entry in fs::read_dir(root).with_context(|| format!("read {}", root.display()))? {
        let path = entry?.path();
        if path.is_dir() {
            hash_tree(&path, out)?;
        } else {
            out.insert(path.display().to_string(), sha256_file(&path)?);
        }
    }
    Ok(())
}

/// Run all three cases in a newly-created output directory.
pub fn run(config: &Config) -> Result<RunReport> {
    for p in [
        &config.gmsh,
        &config.elmergrid,
        &config.elmersolver,
        &config.bar_geo,
        &config.case_sif,
        &config.output_dir,
    ] {
        if !p.is_absolute() {
            bail!("all executable, template, and output paths must be absolute");
        }
    }
    if config.output_dir.exists() {
        bail!(
            "refusing to overwrite existing output directory {}",
            config.output_dir.display()
        );
    }
    fs::create_dir(&config.output_dir).context("create output directory")?;
    match run_new(config) {
        Ok(report) => Ok(report),
        Err(error) => {
            let mut artifacts = BTreeMap::new();
            let hash_error = hash_tree(&config.output_dir, &mut artifacts)
                .err()
                .map(|e| e.to_string());
            let failure = serde_json::json!({
                "status": "failed", "error": format!("{error:#}"),
                "source_identity": fs::read_to_string(config.output_dir.join("git-revision.stdout")).ok(),
                "source_status": fs::read_to_string(config.output_dir.join("git-status.stdout")).ok(),
                "input_sha256": {"geo": sha256_file(&config.bar_geo).ok(), "sif": sha256_file(&config.case_sif).ok()},
                "partial_artifact_sha256": artifacts, "artifact_hash_error": hash_error,
                "omp_num_threads": REFERENCE_THREADS, "ompi_mca_btl": "self"
            });
            fs::write(
                config.output_dir.join("report.json"),
                serde_json::to_vec_pretty(&failure)?,
            )?;
            Err(error)
        }
    }
}

fn run_new(config: &Config) -> Result<RunReport> {
    let revision = git_output(config, &["rev-parse", "HEAD"], "git-revision")?;
    if revision.len() != 40 || !revision.bytes().all(|b| b.is_ascii_hexdigit()) {
        bail!("invalid source revision");
    }
    let source_status = git_output(config, &["status", "--porcelain"], "git-status")?;
    let geo = fs::read(&config.bar_geo)?;
    let sif = fs::read(&config.case_sif)?;
    if geo != include_bytes!("../fixtures/bar.geo") || sif != include_bytes!("../fixtures/case.sif")
    {
        bail!("input differs from the compiled canonical bar reference");
    }
    let source_sha256 = format!(
        "geo:{:x} sif:{:x}",
        Sha256::digest(&geo),
        Sha256::digest(&sif)
    );
    let mut cases = Vec::new();
    let mut timings_ms = Vec::new();
    let mut artifact_sha256 = BTreeMap::new();
    let mut solver_library_sha256 = BTreeMap::new();
    let mut mesh_node_counts = Vec::new();
    hash_tree(&std::env::current_exe()?, &mut artifact_sha256)?;
    hash_tree(&config.gmsh, &mut artifact_sha256)?;
    hash_tree(&config.elmergrid, &mut artifact_sha256)?;
    hash_tree(&config.elmersolver, &mut artifact_sha256)?;
    let solver_root = config
        .elmersolver
        .parent()
        .and_then(Path::parent)
        .context("ElmerSolver must be under <prefix>/bin")?;
    hash_tree(
        &solver_root.join("lib/elmersolver"),
        &mut solver_library_sha256,
    )?;
    hash_tree(
        &solver_root.join("share/elmersolver/lib"),
        &mut solver_library_sha256,
    )?;
    let tool_versions = vec![
        version(
            &config.gmsh,
            false,
            &config.output_dir,
            &config.output_dir.join("gmsh-version.log"),
            config.timeout,
        )?,
        version(
            &config.elmergrid,
            true,
            &config.output_dir,
            &config.output_dir.join("elmergrid-version.log"),
            config.timeout,
        )?,
        version(
            &config.elmersolver,
            false,
            &config.output_dir,
            &config.output_dir.join("elmersolver-version.log"),
            config.timeout,
        )?,
    ];
    for size in MESH_SIZES_M {
        let case_started = Instant::now();
        let name = format!("mesh-{size:.7}");
        let dir = config.output_dir.join(&name);
        fs::create_dir(&dir)?;
        fs::write(dir.join("bar.geo"), &geo)?;
        fs::write(dir.join("case.sif"), &sif)?;
        run_process(
            &config.gmsh,
            &[
                "bar.geo",
                "-3",
                "-setnumber",
                "h",
                &size.to_string(),
                "-format",
                "msh2",
                "-o",
                "bar.msh",
                "-nt",
                REFERENCE_THREADS,
            ],
            &dir,
            &dir.join("gmsh.log"),
            config.timeout,
        )?;
        run_process(
            &config.elmergrid,
            &["14", "2", "bar.msh"],
            &dir,
            &dir.join("elmergrid.log"),
            config.timeout,
        )?;
        run_process(
            &config.elmersolver,
            &["case.sif"],
            &dir,
            &dir.join("elmersolver.log"),
            config.timeout,
        )?;
        let log = fs::read(dir.join("elmersolver.log"))?;
        let scalars =
            fs::read(dir.join("scalars.dat")).context("Elmer case must emit scalars.dat")?;
        let names = fs::read(dir.join("scalars.dat.names"))
            .context("Elmer case must emit scalars.dat.names")?;
        let measurement = parse_elmer_outputs_named(&log, &scalars, Some(&names))?;
        let header = fs::read_to_string(dir.join("bar/mesh.header"))?;
        let nodes: usize = header
            .split_whitespace()
            .next()
            .context("empty mesh header")?
            .parse()?;
        if nodes == 0 || mesh_node_counts.last().is_some_and(|last| nodes <= *last) {
            bail!("mesh refinement did not increase node count");
        }
        mesh_node_counts.push(nodes);
        timings_ms.push(case_started.elapsed().as_millis());
        cases.push(CaseResult {
            mesh_size_m: size,
            temperature_rise_k: measurement.peak_temperature_k - AMBIENT_K,
            measurement,
        });
    }
    validate_measurements(&cases)?;
    hash_tree(&config.output_dir, &mut artifact_sha256)?;
    let report = RunReport {
        status: "reference_pass".into(),
        cases,
        source_sha256,
        omp_num_threads: Some(REFERENCE_THREADS.into()),
        source_identity: Some(revision),
        dirty: Some((!source_status.is_empty()).to_string()),
        tool_versions,
        timings_ms,
        artifact_sha256,
        solver_library_sha256,
        mesh_node_counts,
    };
    fs::write(
        config.output_dir.join("report.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_real_elmer_labels_and_scalars() {
        let m = parse_elmer_outputs_named(
            include_bytes!("../tests/fixtures/mesh-0.0005000/elmersolver.log"),
            include_bytes!("../tests/fixtures/mesh-0.0005000/scalars.dat"),
            Some(include_bytes!(
                "../tests/fixtures/mesh-0.0005000/scalars.dat.names"
            )),
        )
        .unwrap();
        assert!(
            (m.resistance_ohm - EXPECTED_RESISTANCE_OHM).abs() / EXPECTED_RESISTANCE_OHM < 1e-4
        );
        assert!((m.power_w - EXPECTED_POWER_W).abs() / EXPECTED_POWER_W < 1e-4);
        assert!((m.peak_temperature_k - 300.4).abs() < 0.001);
    }

    #[test]
    fn parser_rejects_missing_nonfinite_and_malformed_measurements() {
        assert!(
            parse_elmer_outputs_named(b"Effective Resistance : nope", b"0 1 nope 3", None).is_err()
        );
        assert!(
            parse_elmer_outputs_named(b"Effective Resistance : nope", b"0 1 2 3", None).is_err()
        );
    }

    #[test]
    fn validator_rejects_duplicate_mesh_measurements() {
        let m = Measurement {
            resistance_ohm: EXPECTED_RESISTANCE_OHM,
            power_w: EXPECTED_POWER_W,
            peak_temperature_k: AMBIENT_K + EXPECTED_RISE_K,
        };
        let cases = vec![
            CaseResult {
                mesh_size_m: 0.1,
                measurement: m.clone(),
                temperature_rise_k: EXPECTED_RISE_K,
            },
            CaseResult {
                mesh_size_m: 0.1,
                measurement: m.clone(),
                temperature_rise_k: EXPECTED_RISE_K,
            },
            CaseResult {
                mesh_size_m: 0.2,
                measurement: m,
                temperature_rise_k: EXPECTED_RISE_K,
            },
        ];
        assert!(validate_measurements(&cases).is_err());
    }

    #[test]
    fn runner_refuses_stale_output_directory_before_launching_solver() {
        let root = std::env::temp_dir().join(format!("zapote-thermal-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let config = Config {
            gmsh: root.join("gmsh"),
            elmergrid: root.join("grid"),
            elmersolver: root.join("solver"),
            output_dir: root.clone(),
            bar_geo: root.join("bar.geo"),
            case_sif: root.join("case.sif"),
            timeout: Duration::from_secs(1),
        };
        assert!(run(&config).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn captured_live_fixture_replay_fails_closed_when_scalar_or_log_changes() {
        let base = "tests/fixtures/mesh-0.0005000/";
        let log = include_bytes!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/mesh-0.0005000/elmersolver.log"
        ));
        let scalars = include_bytes!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/mesh-0.0005000/scalars.dat"
        ));
        let names = include_bytes!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/mesh-0.0005000/scalars.dat.names"
        ));
        let measurement = parse_elmer_outputs_named(log, scalars, Some(names)).unwrap();
        assert!(
            (measurement.power_w - EXPECTED_POWER_W).abs() / EXPECTED_POWER_W < 1e-4,
            "{base}"
        );
        let mut bad_names = names.to_vec();
        bad_names.retain(|b| *b != b'1');
        assert!(parse_elmer_outputs_named(log, scalars, Some(&bad_names)).is_err());
        let bad_log =
            String::from_utf8_lossy(log).replace("4.6400000000000148", "4.0000000000000000");
        assert!(parse_elmer_outputs_named(bad_log.as_bytes(), scalars, Some(names)).is_err());
    }

    #[test]
    fn process_failure_and_timeout_are_reported() {
        let root =
            std::env::temp_dir().join(format!("zapote-thermal-process-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        assert!(run_process(
            Path::new("/bin/sh"),
            &["-c", "exit 7"],
            &root,
            &root.join("failure.log"),
            Duration::from_secs(1)
        )
        .is_err());
        assert!(run_process(
            Path::new("/bin/sh"),
            &["-c", "sleep 2"],
            &root,
            &root.join("timeout.log"),
            Duration::from_millis(20)
        )
        .is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn failed_preflight_retains_authoritative_report_and_command() {
        let root =
            std::env::temp_dir().join(format!("zapote-thermal-failed-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        for dir in [
            "tools/bin",
            "tools/lib/elmersolver",
            "tools/share/elmersolver/lib",
        ] {
            fs::create_dir_all(root.join(dir)).unwrap();
        }
        let solver = root.join("tools/bin/ElmerSolver");
        fs::write(&solver, b"never executed: the first tool fails").unwrap();
        let config = Config {
            gmsh: "/usr/bin/false".into(),
            elmergrid: "/usr/bin/false".into(),
            elmersolver: solver,
            output_dir: root.join("attempt"),
            bar_geo: Path::new(env!("CARGO_MANIFEST_DIR")).join("fixtures/bar.geo"),
            case_sif: Path::new(env!("CARGO_MANIFEST_DIR")).join("fixtures/case.sif"),
            timeout: Duration::from_secs(5),
        };
        assert!(run(&config).is_err());
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(config.output_dir.join("report.json")).unwrap())
                .unwrap();
        assert_eq!(report["status"], "failed");
        assert!(report["error"]
            .as_str()
            .unwrap()
            .contains("/usr/bin/false failed"));
        assert!(report["partial_artifact_sha256"]
            .as_object()
            .unwrap()
            .keys()
            .any(|s| s.ends_with("gmsh-version.command.json")));
        assert!(run(&config)
            .unwrap_err()
            .to_string()
            .contains("refusing to overwrite"));
        let mut changed = config.clone();
        changed.output_dir = root.join("modified-input-attempt");
        changed.case_sif = root.join("modified.sif");
        let mut bytes = fs::read(&config.case_sif).unwrap();
        bytes.extend_from_slice(b"\n! edited deck\n");
        fs::write(&changed.case_sif, bytes).unwrap();
        assert!(run(&changed)
            .unwrap_err()
            .to_string()
            .contains("compiled canonical"));
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn timeout_stops_descendant_writers() {
        let root =
            std::env::temp_dir().join(format!("zapote-thermal-descendant-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        let result = run_process(
            Path::new("/bin/sh"),
            &["-c", "(touch ready; while [ ! -f release ]; do sleep 0.02; done; echo escaped > sentinel) & wait"],
            &root,
            &root.join("timeout.log"),
            Duration::from_secs(2),
        );
        assert!(result.unwrap_err().to_string().contains("exceeded timeout"));
        assert!(root.join("ready").exists(), "descendant never started");
        // The write is enabled only after the timeout returned. A scheduling
        // delay before SIGKILL must not masquerade as a surviving descendant.
        fs::write(root.join("release"), b"go").unwrap();
        thread::sleep(Duration::from_millis(250));
        assert!(
            !root.join("sentinel").exists(),
            "descendant survived the timeout"
        );
        assert!(root.join("timeout.command.json").exists());
        assert!(root.join("timeout.stdout").exists());
        fs::remove_dir_all(root).unwrap();
    }
}

pub mod shunt_local;

mod shunt_mesh;

pub mod shunt_assembly;
pub mod shunt_assembly_mesh;
