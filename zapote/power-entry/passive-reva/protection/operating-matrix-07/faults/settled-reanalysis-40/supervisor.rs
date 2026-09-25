//! Reanalyze an already-captured native fault42 gzip without re-simulating.
//! Diagnostic transport only: a successful pipeline never means acceptance.

use std::{
    env, fs,
    fs::File,
    os::unix::fs::FileTypeExt,
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

const USAGE: &str = "supervisor SOURCE_CASE OUTPUT_DIR PIGZ DECODER ADAPTER VALIDATOR [--bypass]";
const DISK_FLOOR_BYTES: u64 = 10 * 1024 * 1024 * 1024;
// The capture deck's 25 ns pacing step is local instrumentation. The adapter
// and validator enforce the separate campaign-wide 1 us positive-gap bound.
const GLOBAL_MAX_GAP_S: f64 = 1e-6;

fn analysis_max_gap(capture_pacing_gap: f64) -> Result<f64, String> {
    if !capture_pacing_gap.is_finite() || capture_pacing_gap <= 0.0 || capture_pacing_gap != 25e-9 {
        return Err("this prepared campaign requires the declared 25 ns local pacing bound".into());
    }
    Ok(GLOBAL_MAX_GAP_S)
}

struct ChildGuard {
    label: &'static str,
    child: Option<Child>,
}

impl ChildGuard {
    fn spawn(label: &'static str, mut command: Command) -> Result<Self, String> {
        let child = command
            .spawn()
            .map_err(|error| format!("spawn {label}: {error}"))?;
        Ok(Self { label, child: Some(child) })
    }

    fn try_wait(&mut self) -> Result<Option<ExitStatus>, String> {
        self.child
            .as_mut()
            .ok_or_else(|| format!("{} already reaped", self.label))?
            .try_wait()
            .map_err(|error| format!("wait {}: {error}", self.label))
    }

    fn kill_reap(&mut self) {
        if let Some(child) = self.child.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        self.kill_reap();
    }
}

fn json_escape(value: &str) -> String {
    let mut out = String::new();
    for ch in value.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            ch if ch < '\u{20}' => out.push_str(&format!("\\u{:04x}", ch as u32)),
            ch => out.push(ch),
        }
    }
    out
}

fn require_file(path: &Path, label: &str) -> Result<(), String> {
    let metadata = fs::metadata(path).map_err(|error| format!("{label} {}: {error}", path.display()))?;
    if !metadata.is_file() {
        return Err(format!("{label} is not a regular file: {}", path.display()));
    }
    Ok(())
}

fn sha256(path: &Path) -> Result<String, String> {
    let value = path.to_str().ok_or_else(|| format!("non-UTF8 path: {}", path.display()))?;
    let output = Command::new("shasum")
        .args(["-a", "256", value])
        .output()
        .map_err(|error| format!("hash {value}: {error}"))?;
    if !output.status.success() {
        return Err(format!("hash failed: {value}"));
    }
    String::from_utf8_lossy(&output.stdout)
        .split_whitespace()
        .next()
        .map(str::to_owned)
        .ok_or_else(|| format!("hash output missing: {value}"))
}

fn jq(path: &Path, filter: &str) -> Result<String, String> {
    let path = path.to_str().ok_or("non-UTF8 JSON path")?;
    let output = Command::new("jq")
        .args(["-er", filter, path])
        .output()
        .map_err(|error| format!("jq {path}: {error}"))?;
    if !output.status.success() {
        return Err(format!("jq filter failed for {path}: {filter}"));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn positive(name: &str, text: &str) -> Result<f64, String> {
    let value = text.parse::<f64>().map_err(|_| format!("invalid {name}"))?;
    if value.is_finite() && value > 0.0 {
        Ok(value)
    } else {
        Err(format!("{name} must be finite and positive"))
    }
}

fn shell_quote(path: &Path) -> Result<String, String> {
    let text = path.to_str().ok_or("non-UTF8 command path")?;
    Ok(format!("'{}'", text.replace('\'', "'\\''")))
}

fn disk_free(path: &Path) -> Result<u64, String> {
    let path = path.to_str().ok_or("non-UTF8 output path")?;
    let output = Command::new("df")
        .args(["-k", path])
        .output()
        .map_err(|error| format!("df: {error}"))?;
    if !output.status.success() {
        return Err("df failed".into());
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let line = stdout
        .lines()
        .nth(1)
        .ok_or("df data missing")?;
    let blocks = line
        .split_whitespace()
        .nth(3)
        .ok_or("df available blocks missing")?
        .parse::<u64>()
        .map_err(|_| "df available blocks invalid".to_string())?;
    Ok(blocks * 1024)
}

fn make_fifo(path: &Path) -> Result<(), String> {
    if path.exists() {
        return Err(format!("refusing existing FIFO/output {}", path.display()));
    }
    let status = Command::new("mkfifo")
        .arg(path)
        .status()
        .map_err(|error| format!("mkfifo {}: {error}", path.display()))?;
    if !status.success() || !fs::metadata(path).map_err(|error| error.to_string())?.file_type().is_fifo() {
        return Err(format!("mkfifo did not create FIFO: {}", path.display()));
    }
    Ok(())
}

fn fresh_output(path: &Path) -> Result<PathBuf, String> {
    if path.exists() {
        if !path.is_dir() {
            return Err(format!("output is not a directory: {}", path.display()));
        }
        if fs::read_dir(path).map_err(|error| error.to_string())?.next().is_some() {
            return Err(format!("output directory is not empty: {}", path.display()));
        }
    } else {
        fs::create_dir_all(path).map_err(|error| format!("create output: {error}"))?;
    }
    fs::canonicalize(path).map_err(|error| format!("canonical output: {error}"))
}

fn hash_entries(case: &Path, entries: &str) -> Result<Vec<(PathBuf, String)>, String> {
    let root = fs::canonicalize(case).map_err(|error| error.to_string())?;
    let mut result = Vec::new();
    for line in entries.lines() {
        let mut fields = line.split('\t');
        let relative = fields.next().ok_or("source hash path missing")?;
        let declared = fields.next().ok_or("source hash missing")?;
        if fields.next().is_some() || relative.is_empty() || relative.starts_with('/') || relative.contains("..") {
            return Err(format!("invalid source-relative hash entry: {relative}"));
        }
        let path = fs::canonicalize(root.join(relative)).map_err(|error| format!("source {relative}: {error}"))?;
        if !path.starts_with(&root) {
            return Err(format!("source escapes case root: {relative}"));
        }
        require_file(&path, "source file")?;
        let actual = sha256(&path)?;
        if actual != declared {
            return Err(format!("source hash mismatch: {relative}"));
        }
        result.push((path, actual));
    }
    if result.is_empty() {
        return Err("source identity contains no files".into());
    }
    Ok(result)
}

fn validate_metadata(case: &Path) -> Result<u64, String> {
    let path = case.join("capture-metadata.json");
    let filter = "(.stop_reason == \"solver_stopped\") and (.points|type == \"number\" and . >= 2 and floor == .) and (.seen_names_mask == 65535) and (.expected_names_mask == 65535) and (.backwards_count == 0) and (.nonfinite_time == false) and (.diagnostic_only == true) and (.accepted == false) and (.export_format == \"ngspice-real-native\") and (.byte_order == \"little\") and (.schema == \"fault42\")";
    jq(&path, filter)?;
    jq(&path, ".points")?.parse::<u64>().map_err(|_| "capture points invalid".into())
}

fn validate_manifest(case: &Path) -> Result<(), String> {
    let path = case.join("manifest.json");
    let filter = "(.case|type == \"string\") and (.output_sha256|type == \"object\") and (.tstop_s|type == \"number\") and ((.mutation_s // .t_fault_s)|type == \"number\") and ((.event_window_s // .prefault_window_s)|type == \"number\")";
    jq(&path, filter)?;
    let entries = jq(&path, ".output_sha256 | to_entries[] | [.key,.value] | @tsv")?;
    let _ = hash_entries(case, &entries)?;
    Ok(())
}

fn manifest_kind(kind: &str) -> &str { if kind == "switch-short" { "sw-short" } else { kind } }

fn validate_manifest_binding(case: &Path, kind: &str, tstop: f64, mutation: f64, event_window: f64) -> Result<(), String> {
    validate_manifest(case)?;
    let manifest = case.join("manifest.json");
    if jq(&manifest, ".case | ascii_downcase")? != manifest_kind(kind) {
        return Err("manifest case does not match immutable run parameters".into());
    }
    let declared_tstop = jq(&manifest, ".tstop_s")?.parse::<f64>().map_err(|_| "manifest tstop invalid")?;
    let declared_mutation = jq(&manifest, "(.mutation_s // .t_fault_s)")?.parse::<f64>().map_err(|_| "manifest mutation invalid")?;
    let declared_window = jq(&manifest, "(.event_window_s // .prefault_window_s)")?.parse::<f64>().map_err(|_| "manifest event window invalid")?;
    if (declared_tstop - tstop).abs() > 1e-15 || (declared_mutation - mutation).abs() > 1e-15 || (declared_window - event_window).abs() > 1e-15 {
        return Err("manifest timing does not match immutable run parameters".into());
    }
    Ok(())
}

fn validate_tools(case: &Path, tools: &[(&str, &Path)]) -> Result<Vec<(String, PathBuf, String)>, String> {
    let identity = case.join("source-identity.json");
    let mut result = Vec::new();
    for (label, actual_path) in tools {
        let expected_path = fs::canonicalize(jq(&identity, &format!(".tools[\"{label}\"].path")).map(PathBuf::from).map_err(|error| error.to_string())?)
            .map_err(|error| format!("source identity tool {label}: {error}"))?;
        let actual_path = fs::canonicalize(actual_path).map_err(|error| format!("tool {label}: {error}"))?;
        require_file(&actual_path, label)?;
        if actual_path != expected_path && *label != "validator" {
            return Err(format!("tool path mismatch for {label}"));
        }
        let expected_hash = jq(&identity, &format!(".tools[\"{label}\"].sha256"))?;
        let actual_hash = sha256(&actual_path)?;
        if actual_hash != expected_hash && *label != "validator" {
            return Err(format!("tool hash mismatch for {label}"));
        }
        result.push(((*label).to_owned(), actual_path, actual_hash));
    }
    Ok(result)
}

fn write_validator_override(out: &Path, case: &Path, actual: &Path) -> Result<(), String> {
    let identity = case.join("source-identity.json");
    let expected_path = jq(&identity, ".tools.validator.path")?;
    let expected_hash = jq(&identity, ".tools.validator.sha256")?;
    let actual_hash = sha256(actual)?;
    let expected_path = fs::canonicalize(expected_path).map_err(|error| format!("validator source path: {error}"))?;
    let actual_path = fs::canonicalize(actual).map_err(|error| format!("validator path: {error}"))?;
    fs::write(out.join("validator-tool-override.json"), format!(
        "{{\n  \"override\":{},\n  \"expected_path\":\"{}\",\n  \"expected_sha256\":\"{}\",\n  \"actual_path\":\"{}\",\n  \"actual_sha256\":\"{}\"\n}}\n",
        expected_path != actual_path || expected_hash != actual_hash,
        json_escape(&expected_path.display().to_string()), json_escape(&expected_hash),
        json_escape(&actual_path.display().to_string()), json_escape(&actual_hash))).map_err(|error| error.to_string())
}

fn validate_capture_stage1(case: &Path, raw: &Path, raw_hash: &str) -> Result<(), String> {
    let receipt = case.join("capture-stage1.json");
    require_file(&receipt, "capture-stage1 receipt")?;
    let expected_bytes = fs::metadata(raw).map_err(|error| error.to_string())?.len();
    let declared_bytes = jq(&receipt, ".raw_trace_bytes")?.parse::<u64>().map_err(|_| "capture-stage1 byte count invalid")?;
    let declared_hash = jq(&receipt, ".raw_trace_sha256")?;
    if jq(&receipt, ".host_success")? != "true" || jq(&receipt, ".pigz_success")? != "true" || declared_bytes != expected_bytes || declared_hash != raw_hash {
        return Err("capture-stage1 receipt does not bind the retained raw trace".into());
    }
    Ok(())
}

fn source_snapshot(case: &Path, points: u64) -> Result<Vec<(String, String)>, String> {
    let identity = case.join("source-identity.json");
    let input = jq(&identity, ".input_files[] | [.path,.sha256] | @tsv")?;
    let mut files = hash_entries(case, &input)?;
    let extra = ["source-identity.json", "capture-metadata.json", "run-parameters.json", "manifest.json", "capture-stage1.json", "raw.trace.raw.gz"];
    for name in extra {
        let path = case.join(name);
        require_file(&path, name)?;
        files.push((fs::canonicalize(&path).map_err(|error| error.to_string())?, sha256(&path)?));
    }
    if fs::metadata(case.join("raw.trace.raw.gz")).map_err(|error| error.to_string())?.len() == 0 || points < 2 {
        return Err("raw trace or source point count is empty".into());
    }
    files.sort_by(|a, b| a.0.cmp(&b.0));
    files.dedup_by(|a, b| a.0 == b.0);
    files.into_iter().map(|(path, hash)| Ok((path.to_string_lossy().into_owned(), hash))).collect()
}

fn write_binding(out: &Path, source: &Path, files: &[(String, String)], tools: &[(String, PathBuf, String)], raw_hash: &str, points: u64) -> Result<(), String> {
    let mut input = String::new();
    for (i, (path, hash)) in files.iter().enumerate() {
        if i > 0 { input.push_str(",\n"); }
        input.push_str(&format!("    {{\"path\":\"{}\",\"sha256\":\"{}\"}}", json_escape(path), hash));
    }
    let mut tool_json = String::new();
    for (i, (label, path, hash)) in tools.iter().enumerate() {
        if i > 0 { tool_json.push_str(",\n"); }
        tool_json.push_str(&format!("    \"{}\": {{\"path\":\"{}\",\"sha256\":\"{}\"}}", json_escape(label), json_escape(&path.display().to_string()), hash));
    }
    fs::write(out.join("source-binding.json"), format!("{{\n  \"source_case\":\"{}\",\n  \"raw_trace_sha256\":\"{}\",\n  \"capture_points\":{},\n  \"input_files\":[\n{}\n  ],\n  \"tools\":{{\n{}\n  }}\n}}\n", json_escape(&source.display().to_string()), raw_hash, points, input, tool_json)).map_err(|error| error.to_string())
}

fn wait_children(children: &mut [&mut ChildGuard], out: &Path, timeout: Duration, labels: &[&str]) -> Result<Vec<ExitStatus>, String> {
    let start = Instant::now();
    let mut statuses: Vec<Option<ExitStatus>> = vec![None; children.len()];
    loop {
        if disk_free(out)? < DISK_FLOOR_BYTES {
            for child in children.iter_mut() { child.kill_reap(); }
            write_partial_status(out, labels, children);
            return Err("disk floor fell below 10 GiB".into());
        }
        for (index, child) in children.iter_mut().enumerate() {
            if statuses[index].is_none() {
                match child.try_wait() {
                    Ok(status) => statuses[index] = status,
                    Err(error) => {
                        for sibling in children.iter_mut() { sibling.kill_reap(); }
                        write_partial_status(out, labels, children);
                        return Err(error);
                    }
                }
            }
        }
        if statuses.iter().all(Option::is_some) {
            return Ok(statuses.into_iter().map(Option::unwrap).collect());
        }
        if start.elapsed() >= timeout {
            for child in children.iter_mut() { child.kill_reap(); }
            write_partial_status(out, labels, children);
            return Err(format!("pipeline exceeded {:?}", timeout));
        }
        thread::sleep(Duration::from_secs(1));
    }
}

fn write_partial_status(out: &Path, labels: &[&str], children: &mut [&mut ChildGuard]) {
    let mut text = String::new();
    for (label, child) in labels.iter().zip(children.iter_mut()) {
        let status = child.try_wait().ok().flatten();
        match status {
            Some(status) => text.push_str(&format!("{label}_rc={} success={}\n", status.code().unwrap_or(-1), status.success())),
            None => text.push_str(&format!("{label}_rc=unknown success=false\n")),
        }
    }
    let _ = fs::write(out.join("pipeline-status.txt"), text);
}

fn write_status(out: &Path, labels: &[&str], statuses: &[ExitStatus]) -> Result<(), String> {
    let mut text = String::new();
    for (label, status) in labels.iter().zip(statuses) {
        text.push_str(&format!("{label}_rc={} success={}\n", status.code().unwrap_or(-1), status.success()));
    }
    fs::write(out.join("pipeline-status.txt"), text).map_err(|error| error.to_string())
}

fn row_count(path: &Path, key: &str) -> Result<u64, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("read {}: {error}", path.display()))?;
    text.split_whitespace()
        .find_map(|field| field.strip_prefix(key))
        .ok_or_else(|| format!("{} missing {key}", path.display()))?
        .parse::<u64>()
        .map_err(|_| format!("{} invalid {key}", path.display()))
}

fn write_receipt(out: &Path, classification: &str, detail: &str, source: &Path, raw_hash: &str, statuses: Option<&[ExitStatus]>, points: u64, transport: bool, validator_success: bool) -> Result<(), String> {
    let status_text = statuses.map(|items| items.iter().map(|status| status.code().unwrap_or(-1).to_string()).collect::<Vec<_>>().join(",")).unwrap_or_else(|| "null".into());
    fs::write(out.join("reanalysis-receipt.json"), format!("{{\n  \"status\":\"REVIEW_PENDING\",\n  \"classification\":\"{}\",\n  \"detail\":\"{}\",\n  \"source_case\":\"{}\",\n  \"raw_trace_sha256\":\"{}\",\n  \"capture_points\":{},\n  \"child_exit_codes\":{},\n  \"transport_complete\":{},\n  \"validator_success\":{},\n  \"acceptance\":false\n}}\n", json_escape(classification), json_escape(detail), json_escape(&source.display().to_string()), raw_hash, points, if status_text == "null" { status_text } else { format!("[{}]", status_text) }, transport, validator_success)).map_err(|error| error.to_string())
}

fn run(source_arg: &str, output_arg: &str, pigz_arg: &str, decoder_arg: &str, adapter_arg: &str, validator_arg: &str, bypass: bool) -> Result<(), String> {
    let source = fs::canonicalize(source_arg).map_err(|error| format!("source case: {error}"))?;
    let output = fresh_output(Path::new(output_arg))?;
    if source == output { return Err("source and output directories must differ".into()); }
    let pigz = fs::canonicalize(pigz_arg).map_err(|error| format!("pigz: {error}"))?;
    let decoder = fs::canonicalize(decoder_arg).map_err(|error| format!("decoder: {error}"))?;
    let adapter = fs::canonicalize(adapter_arg).map_err(|error| format!("adapter: {error}"))?;
    let validator = fs::canonicalize(validator_arg).map_err(|error| format!("validator: {error}"))?;
    for (label, path) in [("pigz", &pigz), ("decoder", &decoder), ("adapter", &adapter), ("validator", &validator)] { require_file(path, label)?; }
    let manifest = source.join("manifest.json");
    let identity = source.join("source-identity.json");
    let parameters = source.join("run-parameters.json");
    require_file(&manifest, "manifest")?; require_file(&identity, "source identity")?; require_file(&parameters, "run parameters")?;
    let points = match validate_metadata(&source) { Ok(points) => points, Err(error) => { let _ = write_receipt(&output, "SOURCE_METADATA_REJECTED", &error, &source, "", None, 0, false, false); return Err(error); } };
    let kind = jq(&parameters, ".kind")?.to_ascii_lowercase();
    let (adapter_kind, validator_kind) = match kind.as_str() { "f2-start" => ("f2-start", "f2-open"), "f2-crest" => ("f2-crest", "f2-open"), "f2-zero" => ("f2-zero", "f2-open"), "switch-short" => ("switch-short", "switch-short"), "diode-short" => ("diode-short", "diode-short"), "both-short" => ("both-short", "both-short"), "bypass-neg" => ("bypass-neg", "f2-open"), _ => return Err(format!("unsupported source kind {kind}")) };
    if jq(&parameters, ".bypass | type")? != "boolean" {
        return Err("run parameters bypass must be a JSON boolean".into());
    }
    let declared_bypass = jq(&parameters, ".bypass | tostring")? == "true";
    if bypass != declared_bypass { return Err("--bypass does not match immutable run parameters".into()); }
    let tstop = positive("tstop_s", &jq(&parameters, ".tstop_s")?)?;
    let mutation = positive("mutation_s", &jq(&parameters, ".mutation_s")?)?;
    let event_window = positive("event_window_s", &jq(&parameters, ".event_window_s")?)?;
    let expected_fault = positive("expected_fault_s", &jq(&parameters, ".expected_fault_s")?)?;
    let observation = positive("observation_s", &jq(&parameters, ".observation_s")?)?;
    let turnoff = positive("turnoff_s", &jq(&parameters, ".turnoff_s")?)?;
    let capture_max_gap = positive("max_gap_s", &jq(&parameters, ".max_gap_s")?)?;
    let analysis_gap = analysis_max_gap(capture_max_gap)?;
    fs::write(output.join("gap-policy.json"), format!("{{\n  \"capture_pacing_max_gap_s\": {:.17e},\n  \"analysis_global_max_gap_s\": {:.17e},\n  \"adapter_and_validator_use_global\": true\n}}\n", capture_max_gap, analysis_gap)).map_err(|error| error.to_string())?;
    let timeout_s = positive("export_timeout_s", &jq(&parameters, ".export_timeout_s")?)?;
    if timeout_s < 300.0 || timeout_s > 900.0 { return Err("export timeout must be 300..900 seconds".into()); }
    validate_manifest_binding(&source, &kind, tstop, mutation, event_window)?;
    let tool_records = validate_tools(&source, &[("pigz", &pigz), ("decoder", &decoder), ("adapter", &adapter), ("validator", &validator)])?;
    let raw = source.join("raw.trace.raw.gz"); require_file(&raw, "raw trace")?;
    let raw_hash = sha256(&raw)?;
    validate_capture_stage1(&source, &raw, &raw_hash)?;
    let files_before = source_snapshot(&source, points)?;
    write_binding(&output, &source, &files_before, &tool_records, &raw_hash, points)?;
    write_validator_override(&output, &source, &validator)?;
    if disk_free(&output)? < DISK_FLOOR_BYTES { return Err("less than 10 GiB free before analysis".into()); }
    let adapter_fifo = output.join("adapter.raw.fifo"); let checked_fifo = output.join("checked.fifo");
    let mut fifos = Vec::new();
    for path in [&adapter_fifo, &checked_fifo] {
        if let Err(error) = make_fifo(path) {
            for created in &fifos { let _ = fs::remove_file(created); }
            return Err(error);
        }
        fifos.push(path.clone());
    }
    let result: Result<(), String> = (|| {
        let validator_script = format!("exec {} --end-s {} --expected-fault-s {} --window-s {} --observation-s {} --turnoff-s {} --max-gap-s {} --kind {} --events {}{} < {}", shell_quote(&validator)?, tstop, expected_fault, event_window, observation, turnoff, analysis_gap, validator_kind, shell_quote(&output.join("validator-events.tsv"))?, if bypass { " --bypass" } else { "" }, shell_quote(&checked_fifo)?);
        let mut validator_cmd = Command::new("sh"); validator_cmd.args(["-c", &validator_script]).stdout(Stdio::from(File::create(output.join("validator.stdout")).map_err(|error| error.to_string())?)).stderr(Stdio::from(File::create(output.join("validator.stderr")).map_err(|error| error.to_string())?));
        let mut validator_child = ChildGuard::spawn("validator", validator_cmd)?;
        let mut adapter_cmd = Command::new(&adapter); adapter_cmd.current_dir(&output).args([adapter_fifo.to_str().ok_or("adapter FIFO path")?, checked_fifo.to_str().ok_or("checked FIFO path")?, "/dev/null", "adapter-report.txt", &tstop.to_string(), adapter_kind, &mutation.to_string(), &event_window.to_string(), &analysis_gap.to_string()]).stdout(Stdio::from(File::create(output.join("adapter.stdout")).map_err(|error| error.to_string())?)).stderr(Stdio::from(File::create(output.join("adapter.stderr")).map_err(|error| error.to_string())?));
        let mut adapter_child = ChildGuard::spawn("adapter", adapter_cmd)?;
        let mut decoder_cmd = Command::new(&pigz); decoder_cmd.args(["-dc", raw.to_str().ok_or("raw trace path")?]).stdout(Stdio::piped()).stderr(Stdio::from(File::create(output.join("decompressor.stderr")).map_err(|error| error.to_string())?));
        let mut decompressor = ChildGuard::spawn("decompressor", decoder_cmd)?;
        let decompressor_out = decompressor.child.as_mut().ok_or("decompressor child missing")?.stdout.take().ok_or("decompressor stdout missing")?;
        let decoder_script = format!("exec {} --schema fault42 --byte-order little > {}", shell_quote(&decoder)?, shell_quote(&adapter_fifo)?);
        let mut decoder_cmd = Command::new("sh"); decoder_cmd.args(["-c", &decoder_script]).stdin(Stdio::from(decompressor_out)).stdout(Stdio::from(File::create(output.join("decoder.stdout")).map_err(|error| error.to_string())?)).stderr(Stdio::from(File::create(output.join("decoder.stderr")).map_err(|error| error.to_string())?));
        let mut decoder_child = ChildGuard::spawn("decoder", decoder_cmd)?;
        let labels = ["validator", "adapter", "decompressor", "decoder"];
        let mut children = [&mut validator_child, &mut adapter_child, &mut decompressor, &mut decoder_child];
        let statuses = wait_children(&mut children, &output, Duration::from_secs_f64(timeout_s), &labels)?;
        write_status(&output, &labels, &statuses)?;
        let source_after = source_snapshot(&source, points)?;
        if source_after != files_before { return Err("source identity/hash changed during reanalysis".into()); }
        for (label, path, before_hash) in &tool_records { if sha256(path)? != *before_hash { return Err(format!("tool changed during reanalysis: {label}")); } }
        let raw_after_hash = sha256(&raw)?; if raw_after_hash != raw_hash { return Err("source raw trace changed during reanalysis".into()); }
        let all_success = statuses.iter().all(ExitStatus::success);
        let transport = statuses[1].success() && statuses[2].success() && statuses[3].success();
        if all_success {
            let adapter_rows = row_count(&output.join("adapter-report.txt"), "original_rows=")?;
            let validator_rows = row_count(&output.join("validator.stdout"), "rows=")?;
            if adapter_rows != points || validator_rows != points { return Err(format!("row count mismatch: metadata={points} adapter={adapter_rows} validator={validator_rows}")); }
        }
        let detail = if all_success { "transport complete; validator result remains diagnostic" } else { "one or more pipeline children rejected the stream" };
        write_receipt(&output, if all_success { "COMPLETE_REVIEW_PENDING" } else if transport { "VALIDATOR_REVIEW_PENDING" } else { "PIPELINE_REVIEW_PENDING" }, detail, &source, &raw_hash, Some(&statuses), points, transport, statuses[0].success())?;
        if all_success { Ok(()) } else { Err(detail.into()) }
    })();
    for path in fifos { let _ = fs::remove_file(path); }
    if let Err(error) = &result {
        if !output.join("reanalysis-receipt.json").exists() {
            let _ = write_receipt(&output, "REANALYSIS_FAILED", error, &source, &raw_hash, None, points, false, false);
        } else {
            let _ = fs::write(output.join("reanalysis-failure.txt"), format!("{error}\n"));
        }
    }
    result
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if !(args.len() == 7 || args.len() == 8) || (args.len() == 8 && args[7] != "--bypass") {
        eprintln!("{USAGE}"); std::process::exit(2);
    }
    if let Err(error) = run(&args[1], &args[2], &args[3], &args[4], &args[5], &args[6], args.len() == 8) {
        eprintln!("REANALYSIS_REJECTED {error}"); std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn positive_rejects_nonfinite_and_zero() {
        assert!(positive("x", "1e-6").is_ok());
        assert!(positive("x", "0").is_err());
        assert!(positive("x", "NaN").is_err());
    }

    #[test]
    fn capture_pacing_gap_maps_to_global_outer_gap() {
        assert_eq!(analysis_max_gap(2.5e-8).expect("valid pacing gap"), 1e-6);
        assert!(analysis_max_gap(1e-6).is_err());
        assert!(analysis_max_gap(1e-8).is_err());
        assert!(analysis_max_gap(f64::NAN).is_err());
    }

    #[test]
    fn declared_switch_short_case_matches_cli_kind() {
        assert_eq!("SW-SHORT".to_ascii_lowercase(), manifest_kind("switch-short"));
        assert_eq!("F2-CREST".to_ascii_lowercase(), manifest_kind("f2-crest"));
        assert_ne!("DIODE-SHORT".to_ascii_lowercase(), manifest_kind("switch-short"));
    }

    #[test]
    fn json_escapes_controls() {
        assert_eq!(json_escape("a\t\r\n\u{0001}\""), "a\\t\\r\\n\\u0001\\\"");
    }

    #[test]
    fn child_timeout_kills_and_reaps() {
        let mut command = Command::new("sh"); command.args(["-c", "exec sleep 60"]);
        let mut child = ChildGuard::spawn("sleep", command).unwrap();
        let out = env::temp_dir();
        assert!(wait_children(&mut [&mut child], &out, Duration::from_millis(20), &["sleep"]).is_err());
        assert!(child.try_wait().unwrap().is_some());
    }

    #[test]
    fn fifo_is_verified() {
        let path = env::temp_dir().join(format!("m07-reanalysis-fifo-{}", std::process::id()));
        let _ = fs::remove_file(&path);
        make_fifo(&path).unwrap();
        assert!(fs::metadata(&path).unwrap().file_type().is_fifo());
        fs::remove_file(path).unwrap();
    }
}
