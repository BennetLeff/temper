//! Bounded single-case supervisor for native fault42 capture.
//!
//! This is a diagnostic transport candidate. It retains one native raw42 gzip,
//! decodes it into the event-aware adapter, and streams checked17 into the
//! event-aware validator. It never turns a validator result into acceptance.

use std::{
    env, fs,
    fs::File,
    os::unix::fs::FileTypeExt,
    os::unix::io::{AsRawFd, RawFd},
    os::unix::process::CommandExt,
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

const USAGE: &str = "supervisor CASE NATIVE_HOST PIGZ DECODER ADAPTER VALIDATOR TSTOP KIND MUTATION_S EVENT_WINDOW EXPECTED_FAULT_S OBSERVATION_S TURNOFF_S MAX_GAP_S WALL_SECONDS EXPORT_TIMEOUT [--bypass]";
const DISK_FLOOR_BYTES: u64 = 10 * 1024 * 1024 * 1024;

extern "C" { fn fcntl(fd: i32, cmd: i32, ...) -> i32; }
const F_GETFD: i32 = 1;
const F_SETFD: i32 = 2;
const FD_CLOEXEC: i32 = 1;

struct ChildGuard { label: &'static str, child: Option<Child> }
impl ChildGuard {
    fn spawn(label: &'static str, mut command: Command) -> Result<Self, String> {
        let child = command.spawn().map_err(|e| format!("spawn {label}: {e}"))?;
        Ok(Self { label, child: Some(child) })
    }
    fn try_wait(&mut self) -> Result<Option<ExitStatus>, String> {
        self.child.as_mut().ok_or_else(|| format!("{} already reaped", self.label))?.try_wait().map_err(|e| format!("wait {}: {e}", self.label))
    }
    fn kill_reap(&mut self) { if let Some(child) = self.child.as_mut() { let _ = child.kill(); let _ = child.wait(); } }
}
impl Drop for ChildGuard { fn drop(&mut self) { self.kill_reap(); } }

fn positive(name: &str, value: &str) -> Result<f64, String> {
    let n = value.parse::<f64>().map_err(|_| format!("invalid {name}"))?;
    if n.is_finite() && n > 0.0 { Ok(n) } else { Err(format!("{name} must be finite and positive")) }
}
fn require_file(path: &Path, label: &str) -> Result<(), String> {
    let meta = fs::metadata(path).map_err(|e| format!("{label} {}: {e}", path.display()))?;
    if !meta.is_file() { return Err(format!("{label} is not a regular file: {}", path.display())); }
    Ok(())
}
fn sha256(path: &Path) -> Result<String, String> {
    let value = path.to_str().ok_or("non-UTF8 hash path")?;
    let out = Command::new("shasum").args(["-a", "256", value]).output().map_err(|e| format!("hash {}: {e}", path.display()))?;
    if !out.status.success() { return Err(format!("hash failed for {}", path.display())); }
    String::from_utf8_lossy(&out.stdout).split_whitespace().next().map(str::to_owned).ok_or_else(|| format!("missing hash for {}", path.display()))
}
fn json_escape(value: &str) -> String {
    let mut out = String::new();
    for ch in value.chars() { match ch { '\\' => out.push_str("\\\\"), '"' => out.push_str("\\\""), '\n' => out.push_str("\\n"), '\r' => out.push_str("\\r"), '\t' => out.push_str("\\t"), ch if ch < '\u{20}' => out.push_str(&format!("\\u{:04x}", ch as u32)), ch => out.push(ch) } }
    out
}
fn include_token(line: &str) -> Result<Option<String>, String> {
    let line = line.trim(); if line.is_empty() || line.starts_with('*') || line.starts_with(';') { return Ok(None); }
    let mut fields = line.split_whitespace(); let directive = fields.next().unwrap_or("");
    if directive.eq_ignore_ascii_case(".lib") || directive.eq_ignore_ascii_case(".inc") { return Err(format!("unsupported source directive: {line}")); }
    if !directive.eq_ignore_ascii_case(".include") { return Ok(None); }
    let token = fields.next().ok_or_else(|| format!("missing include path: {line}"))?;
    if fields.next().is_some() { return Err(format!("unsupported include syntax: {line}")); }
    let token = token.trim_matches(['\'', '"']); if token.is_empty() { return Err("empty include path".into()); }
    Ok(Some(token.to_owned()))
}
fn collect_inputs(root: &Path, path: &Path, seen: &mut Vec<PathBuf>) -> Result<(), String> {
    let root = fs::canonicalize(root).map_err(|e| format!("case root: {e}"))?;
    let canonical = fs::canonicalize(path).map_err(|e| format!("include {}: {e}", path.display()))?;
    if !canonical.starts_with(&root) { return Err(format!("include escapes case root: {}", canonical.display())); }
    if seen.iter().any(|p| p == &canonical) { return Ok(()); }
    require_file(&canonical, "included source")?; seen.push(canonical.clone());
    let bytes = fs::read(&canonical).map_err(|e| format!("read {}: {e}", canonical.display()))?;
    let text = String::from_utf8(bytes).map_err(|_| format!("non-UTF8 source {}", canonical.display()))?;
    for line in text.lines() { if let Some(token) = include_token(line)? { collect_inputs(&root, &canonical.parent().unwrap_or(&root).join(token), seen)?; } }
    Ok(())
}
fn source_listing(case: &Path) -> Result<Vec<(String, String)>, String> {
    let root = fs::canonicalize(case).map_err(|e| format!("case root: {e}"))?; let mut files = Vec::new();
    collect_inputs(&root, &root.join("case.cir"), &mut files)?;
    let manifest = root.join("manifest.json"); require_file(&manifest, "case manifest")?; files.push(fs::canonicalize(manifest).map_err(|e| e.to_string())?);
    files.sort(); files.dedup(); files.into_iter().map(|p| { let rel = p.strip_prefix(&root).map_err(|e| e.to_string())?.to_string_lossy().into_owned(); Ok((rel, sha256(&p)?)) }).collect()
}
fn validate_case_manifest(case: &Path, expected_case: &str, tstop: f64, mutation: f64, event_window: f64) -> Result<(), String> {
    let manifest = case.join("manifest.json");
    let guard = Command::new("jq").args(["-e", "(.status|type == \"string\") and (.case|type == \"string\") and (.output_sha256|type == \"object\") and (.tstop_s|type == \"number\") and ((.t_fault_s // .mutation_s)|type == \"number\")", manifest.to_str().ok_or("manifest path")?]).output().map_err(|e| format!("jq manifest validation: {e}"))?;
    if !guard.status.success() { return Err("manifest lacks required typed status/output_sha256/tstop/mutation keys".into()); }
    let actual_case = Command::new("jq").args(["-r", ".case", manifest.to_str().ok_or("manifest path")?]).output().map_err(|e| format!("jq manifest case: {e}"))?;
    if String::from_utf8_lossy(&actual_case.stdout).trim().to_ascii_uppercase() != expected_case { return Err("CLI fault kind does not match manifest case".into()); }
    let number = |filter: &str| -> Result<f64, String> {
        let out = Command::new("jq").args(["-r", filter, manifest.to_str().ok_or("manifest path")?]).output().map_err(|e| format!("jq manifest number: {e}"))?;
        if !out.status.success() { return Err(format!("manifest missing {filter}")); }
        String::from_utf8_lossy(&out.stdout).trim().parse::<f64>().map_err(|_| format!("manifest {filter} is not numeric"))
    };
    let manifest_tstop = number(".tstop_s")?; let manifest_mutation = number("(.t_fault_s // .mutation_s)")?;
    if (manifest_tstop - tstop).abs() > 1e-15 || (manifest_mutation - mutation).abs() > 1e-15 { return Err("CLI timing does not match case manifest".into()); }
    let window = Command::new("jq").args(["-r", "(.prefault_window_s // .event_window_s // empty)", manifest.to_str().ok_or("manifest path")?]).output().map_err(|e| format!("jq manifest window: {e}"))?;
    if window.status.success() && !String::from_utf8_lossy(&window.stdout).trim().is_empty() {
        let declared = String::from_utf8_lossy(&window.stdout).trim().parse::<f64>().map_err(|_| "manifest event window is not numeric".to_string())?;
        if (declared - event_window).abs() > 1e-15 { return Err("CLI event window does not match case manifest".into()); }
    }
    let entries = Command::new("jq").args(["-r", ".output_sha256 | to_entries[] | [.key, .value] | @tsv", manifest.to_str().ok_or("manifest path")?]).output().map_err(|e| format!("jq manifest hashes: {e}"))?;
    if !entries.status.success() { return Err("manifest output_sha256 cannot be enumerated".into()); }
    let mut declared_paths = Vec::new();
    for line in String::from_utf8_lossy(&entries.stdout).lines() {
        let mut fields = line.split('\t'); let relative = fields.next().ok_or("manifest hash path missing")?; let expected = fields.next().ok_or("manifest hash missing")?;
        let path = case.join(relative); let canonical = fs::canonicalize(&path).map_err(|e| format!("manifest output {relative}: {e}"))?; let root = fs::canonicalize(case).map_err(|e| e.to_string())?;
        if !canonical.starts_with(&root) { return Err(format!("manifest output escapes case: {relative}")); }
        if sha256(&canonical)? != expected { return Err(format!("manifest output hash mismatch: {relative}")); }
        declared_paths.push(canonical);
    }
    let mut used_paths = Vec::new();
    collect_inputs(case, &case.join("case.cir"), &mut used_paths)?;
    if used_paths.iter().any(|p| !declared_paths.contains(p)) { return Err("manifest omits an executed source/include hash".into()); }
    Ok(())
}
fn ensure_absent(case: &Path) -> Result<(), String> {
    for name in ["initialization.json","source-identity.json","transport-identity.json","run-parameters.json","capture-metadata.json","raw.trace.raw.gz","raw-gzip.stderr","host.stdout","host.stderr","first-invalid.tsv","stage1.exit","capture-stage1.json","decoder.stderr","adapter.stdout","adapter.stderr","adapter-report.txt","validator.stdout","validator.stderr","validator-events.tsv","stage2.exit","result.json","host.raw.fifo","adapter.raw.fifo","checked.fifo"] {
        if case.join(name).exists() { return Err(format!("refusing existing output {}", case.join(name).display())); }
    }
    Ok(())
}
fn make_fifo(path: &Path) -> Result<(), String> {
    if path.exists() { return Err(format!("refusing existing FIFO/output {}", path.display())); }
    let status = Command::new("mkfifo").arg(path).status().map_err(|e| format!("mkfifo: {e}"))?;
    if !status.success() { return Err("mkfifo failed".into()); }
    if !fs::metadata(path).map_err(|e| e.to_string())?.file_type().is_fifo() { return Err(format!("{} is not a FIFO", path.display())); }
    Ok(())
}
fn disk_free(path: &Path) -> Result<u64, String> {
    let out = Command::new("df").args(["-k", path.to_str().ok_or("non-UTF8 case path")?]).output().map_err(|e| format!("df: {e}"))?;
    if !out.status.success() { return Err("df failed".into()); }
    let text = String::from_utf8_lossy(&out.stdout);
    let line = text.lines().nth(1).ok_or("df missing data")?.split_whitespace().nth(3).ok_or("df missing available blocks")?;
    line.parse::<u64>().map(|blocks| blocks * 1024).map_err(|_| "df available blocks invalid".into())
}
fn log_file(case: &Path, name: &str) -> Result<File, String> { File::create(case.join(name)).map_err(|e| format!("create {name}: {e}")) }
fn shell_quote(path: &Path) -> Result<String, String> { let s = path.to_str().ok_or("non-UTF8 path")?; Ok(format!("'{}'", s.replace('\'', "'\\''"))) }
fn install_export_fd(command: &mut Command, fd: RawFd) {
    // Keep the compressor's dynamic stdin descriptor across exec.  Do not
    // force fd 3: Rust's child-error channel and the allocator may use it.
    unsafe {
        command.pre_exec(move || {
            let flags = fcntl(fd, F_GETFD);
            if flags < 0 || fcntl(fd, F_SETFD, flags & !FD_CLOEXEC) < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}
fn write_failure(case: &Path, class: &str, detail: &str) { let _ = fs::write(case.join("result.json"), format!("{{\n  \"status\": \"REVIEW_PENDING\",\n  \"classification\": \"{}\",\n  \"transport_complete\": false,\n  \"detail\": \"{}\"\n}}\n", json_escape(class), json_escape(detail))); }

fn write_identity(case: &Path, tools: &[(&str, &Path)]) -> Result<(), String> {
    let inputs = source_listing(case)?; let mut body = String::new();
    for (i, (name, hash)) in inputs.iter().enumerate() { if i > 0 { body.push_str(",\n"); } body.push_str(&format!("    {{\"path\":\"{}\",\"sha256\":\"{}\"}}", json_escape(name), hash)); }
    let mut tool_body = String::new();
    for (i, (label, path)) in tools.iter().enumerate() { if i > 0 { tool_body.push_str(",\n"); } tool_body.push_str(&format!("    \"{}\": {{\"path\":\"{}\",\"sha256\":\"{}\"}}", label, json_escape(&path.display().to_string()), sha256(path)?)); }
    fs::write(case.join("source-identity.json"), format!("{{\n  \"input_files\": [\n{}\n  ],\n  \"tools\": {{\n{}\n  }}\n}}\n", body, tool_body)).map_err(|e| e.to_string())
}
fn write_parameters(case: &Path, args: &[String], bypass: bool) -> Result<(), String> {
    fs::write(case.join("run-parameters.json"), format!("{{\n  \"tstop_s\": {},\n  \"kind\": \"{}\",\n  \"mutation_s\": {},\n  \"event_window_s\": {},\n  \"expected_fault_s\": {},\n  \"observation_s\": {},\n  \"turnoff_s\": {},\n  \"max_gap_s\": {},\n  \"wall_seconds\": {},\n  \"export_timeout_s\": {},\n  \"bypass\": {}\n}}\n", args[7], json_escape(&args[8]), args[9],args[10],args[11],args[12],args[13],args[14],args[15],args[16],bypass)).map_err(|e| e.to_string())
}
fn validate_capture_metadata(case: &Path) -> Result<(), String> {
    let path = case.join("capture-metadata.json");
    let guard = Command::new("jq").args(["-e", "(.stop_reason == \"solver_stopped\") and (.points|type == \"number\" and . >= 2) and (.diagnostic_only == true) and (.accepted == false) and (.export_format == \"ngspice-real-native\") and (.byte_order == \"little\") and (.schema == \"fault42\") and (.expected_names_mask == 65535) and (.seen_names_mask == 65535) and (.backwards_count == 0) and (.nonfinite_time == false)", path.to_str().ok_or("metadata path")?]).output().map_err(|e| format!("jq capture metadata validation: {e}"))?;
    if !guard.status.success() { return Err("capture metadata failed typed schema/mask/point validation".into()); }
    Ok(())
}

fn capture_points(case: &Path) -> u64 {
    let path = case.join("capture-metadata.json");
    let output = Command::new("jq").args(["-er", ".points | select(type == \"number\")", path.to_str().unwrap_or("")]).output();
    output.ok().filter(|result| result.status.success())
        .and_then(|result| String::from_utf8_lossy(&result.stdout).trim().parse::<f64>().ok())
        .filter(|points| points.is_finite() && *points >= 0.0)
        .map(|points| points as u64)
        .unwrap_or(0)
}

fn record_capture_stage1(case: &Path, host: ExitStatus, pigz: Option<ExitStatus>, metadata: &str) -> Result<(), String> {
    let raw = case.join("raw.trace.raw.gz");
    let (bytes, hash) = match fs::metadata(&raw) {
        Ok(meta) => (meta.len(), Some(sha256(&raw)?)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (0, None),
        Err(error) => return Err(format!("read raw trace for stage-1 receipt: {error}")),
    };
    let pigz_code = pigz.and_then(|status| status.code()).unwrap_or(-1);
    fs::write(case.join("stage1.exit"), format!("host_rc={} pigz_rc={}\n", host.code().unwrap_or(-1), pigz_code))
        .map_err(|error| format!("write stage-1 exit receipt: {error}"))?;
    fs::write(case.join("capture-stage1.json"), format!(
        "{{\n  \"host_success\": {},\n  \"pigz_success\": {},\n  \"host_rc\": {},\n  \"pigz_rc\": {},\n  \"metadata_status\": \"{}\",\n  \"raw_trace_bytes\": {},\n  \"raw_trace_sha256\": {}\n}}\n",
        host.success(), pigz.is_some_and(|status| status.success()), host.code().unwrap_or(-1), pigz_code,
        json_escape(metadata), bytes, hash.map_or_else(|| "null".into(), |value| format!("\"{value}\""))))
        .map_err(|error| format!("write stage-1 capture receipt: {error}"))?;
    Ok(())
}

fn verify_point_counts(case: &Path) -> Result<(), String> {
    let metadata = Command::new("jq").args(["-er", ".points", case.join("capture-metadata.json").to_str().ok_or("metadata path")?]).output().map_err(|e| e.to_string())?;
    if !metadata.status.success() { return Err("cannot read native point count".into()); }
    let expected: u64 = String::from_utf8_lossy(&metadata.stdout).trim().parse().map_err(|_| "invalid native point count")?;
    let adapter = fs::read_to_string(case.join("adapter-report.txt")).map_err(|e| e.to_string())?;
    let validator = fs::read_to_string(case.join("validator.stdout")).map_err(|e| e.to_string())?;
    for (label, text, key) in [("adapter", adapter.as_str(), "original_rows="), ("validator", validator.as_str(), "rows=")] {
        let count = text.split_whitespace().find_map(|s| s.strip_prefix(key)).ok_or_else(|| format!("{label} omitted row count"))?.parse::<u64>().map_err(|_| format!("{label} row count invalid"))?;
        if count != expected { return Err(format!("{label} rows {count} differ from native points {expected}")); }
    }
    Ok(())
}

fn wait_capture(host: &mut ChildGuard, compressor: &mut ChildGuard, case: &Path, timeout: Duration) -> Result<(ExitStatus, ExitStatus), String> {
    let start = Instant::now();
    loop {
        if disk_free(case)? < DISK_FLOOR_BYTES { host.kill_reap(); compressor.kill_reap(); return Err("disk floor fell below 10 GiB".into()); }
        if let Some(status) = host.try_wait()? {
            if !status.success() {
                compressor.kill_reap();
                let pigz_status = compressor.try_wait()?;
                if let Err(receipt_error) = record_capture_stage1(case, status, pigz_status, "native_host_failed") {
                    return Err(format!("native host failed: {status}; {receipt_error}"));
                }
                return Err(format!("native host failed: {status}"));
            }
            // Inspect metadata before waiting on the FIFO. A missing/zero-point
            // capture is an early host failure: kill the blocked compressor.
            // A positive-point capture (for example a wall-limited host) has
            // real bytes to retain, so drain pigz to EOF before rejecting the
            // semantic metadata status.
            let metadata_result = validate_capture_metadata(case);
            let points = capture_points(case);
            if metadata_result.is_err() && points == 0 {
                compressor.kill_reap();
                let pigz_status = compressor.try_wait()?;
                let metadata_error = metadata_result.expect_err("metadata_result is known to be an error");
                if let Err(receipt_error) = record_capture_stage1(case, status, pigz_status, "metadata_missing_or_zero_points") {
                    return Err(format!("{metadata_error}; {receipt_error}"));
                }
                return Err(metadata_error);
            }
            let mut rest = [compressor];
            let statuses = match wait_children(&mut rest, case, timeout.saturating_sub(start.elapsed()), true) {
                Ok(statuses) => statuses,
                Err(error) => {
                    let pigz_status = rest[0].try_wait().ok().flatten();
                    if let Err(receipt_error) = record_capture_stage1(case, status, pigz_status, "positive_points_drain_failed") {
                        return Err(format!("{error}; {receipt_error}"));
                    }
                    return Err(error);
                }
            };
            let pigz_status = statuses[0];
            let metadata_status = if metadata_result.is_ok() { "valid" } else { "positive_points_semantic_rejection" };
            if let Err(receipt_error) = record_capture_stage1(case, status, Some(pigz_status), metadata_status) {
                return Err(receipt_error);
            }
            if let Err(error) = metadata_result { return Err(error); }
            return Ok((status, pigz_status));
        }
        if let Some(status) = compressor.try_wait()? {
            if !status.success() { host.kill_reap(); return Err(format!("raw pigz failed before host: {status}")); }
        }
        if start.elapsed() >= timeout { host.kill_reap(); compressor.kill_reap(); return Err("native capture exceeded bounded timeout".into()); }
        thread::sleep(Duration::from_secs(1));
    }
}

fn wait_children(children: &mut [&mut ChildGuard], case: &Path, timeout: Duration, disk_guard: bool) -> Result<Vec<ExitStatus>, String> {
    let start = Instant::now(); let mut statuses: Vec<Option<ExitStatus>> = vec![None; children.len()];
    loop {
        if disk_guard && disk_free(case)? < DISK_FLOOR_BYTES { for child in children.iter_mut() { child.kill_reap(); } return Err("disk floor fell below 10 GiB".into()); }
        for (i, child) in children.iter_mut().enumerate() { if statuses[i].is_none() { statuses[i] = child.try_wait()?; } }
        if statuses.iter().all(Option::is_some) { return Ok(statuses.into_iter().map(Option::unwrap).collect()); }
        if start.elapsed() >= timeout { for child in children.iter_mut() { child.kill_reap(); } return Err(format!("child group exceeded {:?}", timeout)); }
        thread::sleep(Duration::from_secs(1));
    }
}
fn run_case(args: &[String]) -> Result<(), String> {
    if !(args.len() == 17 || args.len() == 18) { return Err(USAGE.into()); }
    let bypass = args.get(17).is_some_and(|v| v == "--bypass"); if args.len() == 18 && !bypass { return Err("only --bypass is supported as optional flag".into()); }
    let case = fs::canonicalize(&args[1]).map_err(|e| format!("case: {e}"))?; ensure_absent(&case)?;
    let path = |i: usize, label: &str| -> Result<PathBuf, String> { let p = fs::canonicalize(&args[i]).map_err(|e| format!("{label}: {e}"))?; require_file(&p,label)?; Ok(p) };
    let host=path(2,"native host")?; let pigz=path(3,"pigz")?; let decoder=path(4,"fault42 decoder")?; let adapter=path(5,"event-aware adapter")?; let validator=path(6,"event-aware validator")?;
    for (name, value) in [("TSTOP",&args[7]),("MUTATION_S",&args[9]),("EVENT_WINDOW",&args[10]),("EXPECTED_FAULT_S",&args[11]),("OBSERVATION_S",&args[12]),("TURNOFF_S",&args[13]),("MAX_GAP_S",&args[14]),("WALL_SECONDS",&args[15]),("EXPORT_TIMEOUT",&args[16])] { positive(name,value)?; }
    let requested_kind = args[8].to_ascii_lowercase();
    let (adapter_kind, validator_kind) = match requested_kind.as_str() {
        "f2-start" => ("f2-start", "f2-open"),
        "f2-crest" => ("f2-crest", "f2-open"),
        "f2-zero" => ("f2-zero", "f2-open"),
        "switch-short" => ("switch-short", "switch-short"),
        "diode-short" => ("diode-short", "diode-short"),
        "both-short" => ("both-short", "both-short"),
        "bypass-neg" => ("bypass-neg", "f2-open"),
        _ => return Err(format!("unsupported planned fault kind {}", args[8])),
    };
    if (requested_kind == "bypass-neg") != bypass { return Err("--bypass is required exactly for bypass-neg".into()); }
    let scripts = env::var("SPICE_SCRIPTS").map_err(|_| "SPICE_SCRIPTS must be set explicitly".to_string())?;
    if !Path::new(&scripts).is_dir() { return Err(format!("SPICE_SCRIPTS is not a directory: {scripts}")); }
    let spinit = Path::new(&scripts).join("spinit");
    require_file(&spinit, "SPICE_SCRIPTS/spinit")?;
    let spinit_hash = sha256(&spinit)?;
    fs::write(case.join("initialization.json"), format!("{{\"scripts\":\"{}\",\"spinit_sha256\":\"{}\"}}\n", json_escape(&scripts), spinit_hash)).map_err(|e| e.to_string())?;
    require_file(&case.join("case.cir"),"case deck")?; require_file(&case.join("manifest.json"),"case manifest")?;
    let tstop=args[7].parse::<f64>().map_err(|_| "invalid TSTOP".to_string())?; let mutation=args[9].parse::<f64>().map_err(|_| "invalid MUTATION_S".to_string())?; let event_window=args[10].parse::<f64>().map_err(|_| "invalid EVENT_WINDOW".to_string())?;
    let expected_case = match requested_kind.as_str() { "f2-start" => "F2-START", "f2-crest" => "F2-CREST", "f2-zero" => "F2-ZERO", "switch-short" => "SW-SHORT", "diode-short" => "DIODE-SHORT", "both-short" => "BOTH-SHORT", "bypass-neg" => "BYPASS-NEG", _ => unreachable!() };
    validate_case_manifest(&case,expected_case,tstop,mutation,event_window)?;
    write_identity(&case,&[("native_host",&host),("pigz",&pigz),("decoder",&decoder),("adapter",&adapter),("validator",&validator)])?; write_parameters(&case,args,bypass)?;
    if disk_free(&case)? < DISK_FLOOR_BYTES { return Err("less than 10 GiB free before launch".into()); }
    let adapter_fifo=case.join("adapter.raw.fifo"); let checked_fifo=case.join("checked.fifo"); let raw_gz=case.join("raw.trace.raw.gz");
    let mut created=Vec::new(); for p in [&adapter_fifo,&checked_fifo] { if let Err(e)=make_fifo(p) { for q in &created { let _=fs::remove_file(q); } return Err(e); } created.push(p.to_path_buf()); }
    let before=source_listing(&case)?; let tool_before: Vec<(PathBuf,String)> = [host.clone(),pigz.clone(),decoder.clone(),adapter.clone(),validator.clone()].into_iter().map(|p| { let h=sha256(&p)?; Ok((p,h)) }).collect::<Result<_,String>>()?;
    let result: Result<(), String>=(|| {
        let mut compressor_cmd=Command::new(&pigz);
        compressor_cmd.args(["-p", "4", "-c"])
            .stdin(Stdio::piped())
            .stdout(File::create(&raw_gz).map_err(|e| format!("create raw gzip: {e}"))?)
            .stderr(Stdio::from(log_file(&case,"raw-gzip.stderr")?));
        let mut compressor=ChildGuard::spawn("raw pigz",compressor_cmd)?;
        let write_end=compressor.child.as_mut().ok_or("raw pigz child missing")?.stdin.take().ok_or("raw pigz stdin pipe missing")?;
        let export_fd=write_end.as_raw_fd();
        let export_path=format!("/dev/fd/{export_fd}");
        let mut host_cmd=Command::new(&host); host_cmd.current_dir(&case).args(["case.cir",&args[15],&args[7],&export_path,"first-invalid.tsv"]).stdout(Stdio::from(log_file(&case,"host.stdout")?)).stderr(Stdio::from(log_file(&case,"host.stderr")?));
        install_export_fd(&mut host_cmd, export_fd);
        let mut host_child=match ChildGuard::spawn("native host",host_cmd) {
            Ok(child) => { drop(write_end); child }
            Err(error) => { drop(write_end); compressor.kill_reap(); return Err(error); }
        };
        fs::write(case.join("transport-identity.json"), format!("{{\n  \"transport\": \"anonymous-pipe-dynamic-fd\",\n  \"native_export_path\": \"{}\",\n  \"compressor_stdin_fd\": {},\n  \"shell_or_fifo\": false\n}}\n", json_escape(&export_path), export_fd)).map_err(|e| format!("write transport identity: {e}"))?;
        let statuses=wait_capture(&mut host_child,&mut compressor,&case,Duration::from_secs_f64(args[15].parse::<f64>().unwrap()+args[16].parse::<f64>().unwrap()+10.0))?; fs::write(case.join("stage1.exit"),format!("host_rc={} pigz_rc={}\n",statuses.0.code().unwrap_or(-1),statuses.1.code().unwrap_or(-1))).map_err(|e|e.to_string())?; if !statuses.0.success() || !statuses.1.success() { return Err("native capture or pigz failed".into()); }
        let validator_script = format!("exec {} --end-s {} --expected-fault-s {} --window-s {} --observation-s {} --turnoff-s {} --max-gap-s {} --kind {} --events validator-events.tsv{} < {}", shell_quote(&validator)?, args[7], args[11], args[10], args[12], args[13], args[14], validator_kind, if bypass { " --bypass" } else { "" }, shell_quote(&checked_fifo)?);
        let mut validator_cmd=Command::new("sh"); validator_cmd.current_dir(&case).args(["-c",&validator_script]).stdout(Stdio::from(log_file(&case,"validator.stdout")?)).stderr(Stdio::from(log_file(&case,"validator.stderr")?)); let mut validator_child=ChildGuard::spawn("event-aware validator",validator_cmd)?;
        let mut adapter_cmd=Command::new(&adapter); adapter_cmd.current_dir(&case).args([adapter_fifo.to_str().ok_or("adapter FIFO")?,checked_fifo.to_str().ok_or("checked FIFO")?,"/dev/null","adapter-report.txt",&args[7],adapter_kind,&args[9],&args[10],&args[14]]).stdout(Stdio::from(log_file(&case,"adapter.stdout")?)).stderr(Stdio::from(log_file(&case,"adapter.stderr")?)); let mut adapter_child=ChildGuard::spawn("event-aware adapter",adapter_cmd)?;
        let mut decomp_cmd=Command::new(&pigz); decomp_cmd.args(["-dc",raw_gz.to_str().ok_or("raw gzip path")?]).stdout(Stdio::piped()).stderr(Stdio::from(log_file(&case,"decode.stderr")?)); let mut decomp_raw=decomp_cmd.spawn().map_err(|e|format!("spawn raw decompressor: {e}"))?; let decomp_pipe=decomp_raw.stdout.take().ok_or("raw decompressor pipe")?; let mut decompressor=ChildGuard{label:"raw decompressor",child:Some(decomp_raw)};
        let decoder_script = format!("exec {} --schema fault42 --byte-order little > {}", shell_quote(&decoder)?, shell_quote(&adapter_fifo)?);
        let mut decoder_cmd=Command::new("sh"); decoder_cmd.args(["-c",&decoder_script]).stdin(Stdio::from(decomp_pipe)).stderr(Stdio::from(log_file(&case,"decoder.stderr")?)); let mut decoder_child=ChildGuard::spawn("fault42 decoder",decoder_cmd)?;
        let mut all=[&mut adapter_child,&mut validator_child,&mut decoder_child,&mut decompressor]; let statuses=wait_children(&mut all,&case,Duration::from_secs_f64(args[16].parse::<f64>().unwrap()),true)?; fs::write(case.join("stage2.exit"),format!("adapter_rc={} validator_rc={} decoder_rc={} decompressor_rc={}\n",statuses[0].code().unwrap_or(-1),statuses[1].code().unwrap_or(-1),statuses[2].code().unwrap_or(-1),statuses[3].code().unwrap_or(-1))).map_err(|e|e.to_string())?;
        let after=source_listing(&case)?; if before != after { return Err("source/include closure changed during run".into()); }
        validate_case_manifest(&case,expected_case,tstop,mutation,event_window)?;
        if sha256(&spinit)? != spinit_hash { return Err("ngspice initialization changed during run".into()); }
        if statuses.iter().all(ExitStatus::success) { verify_point_counts(&case)?; }
        for (path, expected) in &tool_before { if sha256(path)? != *expected { return Err(format!("tool changed during run: {}", path.display())); } }
        let raw_size = fs::metadata(&raw_gz).map_err(|e| format!("raw gzip metadata: {e}"))?.len(); if raw_size == 0 { return Err("native raw gzip is empty".into()); }
        let raw_hash=sha256(&raw_gz)?; let transport=statuses[0].success()&&statuses[2].success()&&statuses[3].success(); let successful=transport&&statuses[1].success(); fs::write(case.join("result.json"),format!("{{\n  \"status\": \"REVIEW_PENDING\",\n  \"classification\": \"{}\",\n  \"transport_complete\": {},\n  \"validator_success\": {},\n  \"raw_trace\": \"raw.trace.raw.gz\",\n  \"raw_trace_bytes\": {},\n  \"raw_trace_sha256\": \"{}\",\n  \"acceptance\": false\n}}\n",if successful{"COMPLETE_REVIEW_PENDING"}else if transport{"VALIDATOR_REVIEW_PENDING"}else{"PIPELINE_REVIEW_PENDING"},transport,statuses[1].success(),raw_size,raw_hash)).map_err(|e|e.to_string())?;
        if successful { Ok(()) } else { Err("native fault pipeline child failed or validator rejected".into()) }
    })();
    if let Err(e)=&result { if !case.join("result.json").exists(){write_failure(&case,"native_pipeline_failure",e);} }
    for p in [&adapter_fifo,&checked_fifo] { let _=fs::remove_file(p); }
    result
}
fn main(){let mut args:Vec<String>=env::args().collect();if args.len()==17 || args.len()==18 { for i in [7,9,10,11,12,13,14,15,16] { if let Ok(n)=positive("numeric argument",&args[i]) { args[i]=n.to_string(); } } }if let Err(e)=run_case(&args){eprintln!("SUPERVISOR_REJECTED {e}");std::process::exit(1)}}

#[cfg(test)]
mod tests { use super::*;
    #[test] fn positive_rejects_invalid(){assert!(positive("x","1e-6").is_ok());assert!(positive("x","0").is_err());assert!(positive("x","NaN").is_err());}
    #[test] fn json_controls(){assert_eq!(json_escape("a\t\r\n\u{0001}\""),"a\\t\\r\\n\\u0001\\\"");}
    #[test] fn fifo_is_real(){let d=env::temp_dir().join(format!("m07-native14-{}",std::process::id()));fs::create_dir_all(&d).unwrap();let p=d.join("x");make_fifo(&p).unwrap();assert!(fs::metadata(&p).unwrap().file_type().is_fifo());let _=fs::remove_dir_all(d);}
}

#[cfg(test)]
mod parent_tests {
    use super::*;
    fn dir(name: &str) -> PathBuf {
        let nanos=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let p=env::temp_dir().join(format!("m07-parent-native14-{name}-{}-{nanos}",std::process::id()));
        fs::create_dir(&p).unwrap();p
    }
    fn metadata(p: &Path) {
        fs::write(p.join("capture-metadata.json"),include_str!("../native-capture-13/out/capture-metadata.json")).unwrap();
    }
    #[test] fn metadata_is_typed_and_rejects_nonfinite_and_zero_points() {
        let p=dir("metadata");metadata(&p);assert!(validate_capture_metadata(&p).is_ok());
        let valid=fs::read_to_string(p.join("capture-metadata.json")).unwrap();
        for (a,b) in [("\"points\": 2253","\"points\": 0"),("\"seen_names_mask\": 65535","\"seen_names_mask\": 655350"),("\"nonfinite_time\": false","\"nonfinite_time\": true")] {
            fs::write(p.join("capture-metadata.json"),valid.replace(a,b)).unwrap();assert!(validate_capture_metadata(&p).is_err());
        }
        fs::remove_dir_all(p).unwrap();
    }
    #[test] fn all_independent_row_counts_must_agree() {
        let p=dir("counts");metadata(&p);
        fs::write(p.join("adapter-report.txt"),"original_rows=2253\n").unwrap();
        fs::write(p.join("validator.stdout"),"diagnostic_only=true rows=2253 retained_rows=100\n").unwrap();
        assert!(verify_point_counts(&p).is_ok());
        fs::write(p.join("validator.stdout"),"diagnostic_only=true rows=2252 retained_rows=100\n").unwrap();
        assert!(verify_point_counts(&p).unwrap_err().contains("differ"));fs::remove_dir_all(p).unwrap();
    }
    #[test] fn empty_manifest_hash_map_cannot_authorize_executed_source() {
        let p=dir("closure");fs::write(p.join("case.cir"),"* case\n.include child.inc\n.end\n").unwrap();fs::write(p.join("child.inc"),"* model\n").unwrap();
        fs::write(p.join("manifest.json"),r#"{"status":"TEST_ONLY","case":"F2-START","tstop_s":0.089,"t_fault_s":0.075,"prefault_window_s":0.01,"output_sha256":{}}"#).unwrap();
        assert!(validate_case_manifest(&p,"F2-START",0.089,0.075,0.01).unwrap_err().contains("omits"));fs::remove_dir_all(p).unwrap();
    }
    #[test] fn timeout_reaps_all_owned_children() {
        let p=dir("timeout");let mut cmd=Command::new("sh");cmd.args(["-c","exec sleep 60"]);let mut child=ChildGuard::spawn("fixture",cmd).unwrap();
        assert!(wait_children(&mut [&mut child],&p,Duration::from_millis(20),false).is_err());
        assert!(child.try_wait().unwrap().is_some());fs::remove_dir_all(p).unwrap();
    }
}

#[cfg(test)]
mod capture_drain_tests {
    use super::*;

    fn dir(name: &str) -> PathBuf {
        let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let path = env::temp_dir().join(format!("m07-native19-{name}-{}-{nanos}", std::process::id()));
        fs::create_dir(&path).unwrap();
        path
    }

    fn wall_limit_metadata(path: &Path, points: u64) {
        fs::write(path.join("capture-metadata.json"), format!(
            "{{\"stop_reason\":\"wall_limit\",\"points\":{points},\"first_invalid\":false,\"seen_names_mask\":65535,\"expected_names_mask\":65535,\"duplicate_count\":0,\"backwards_count\":0,\"nonfinite_time\":false,\"diagnostic_only\":true,\"accepted\":false,\"export_format\":\"ngspice-real-native\",\"byte_order\":\"little\",\"schema\":\"fault42\"}}\n"
        )).unwrap();
    }

    fn delayed_gzip_binary() -> PathBuf {
        let path = env::temp_dir().join(format!("m07-native19-slow-gzip-{}", std::process::id()));
        if path.exists() { return path; }
        let source = env::temp_dir().join(format!("m07-native19-slow-gzip-{}.rs", std::process::id()));
        fs::write(&source, include_str!("fixture/slow-gzip.rs")).unwrap();
        let status = Command::new("rustc")
            .args(["--edition=2021", source.to_str().unwrap(), "-O", "-o", path.to_str().unwrap()])
            .status().unwrap();
        assert!(status.success());
        path
    }

    #[test]
    fn positive_wall_limited_capture_drains_and_keeps_readable_gzip() {
        // The old ordering killed the compressor immediately after seeing
        // wall_limit.  This delayed-footer child has already read all FIFO
        // bytes but sleeps before invoking gzip, so that ordering leaves an
        // empty/truncated output.  Keep this as an explicit regression guard.
        let old_case = dir("old-ordering");
        let old_fifo = old_case.join("host.raw.fifo");
        let old_raw = old_case.join("raw.trace.raw.gz");
        make_fifo(&old_fifo).unwrap();
        let delayed = delayed_gzip_binary();
        let old_script = format!("exec '{}' < '{}' > '{}'", delayed.display(), old_fifo.display(), old_raw.display());
        let mut old_compressor = ChildGuard::spawn("old-order delayed gzip", { let mut command = Command::new("sh"); command.args(["-c", &old_script]); command }).unwrap();
        let old_host_script = format!("printf 0123456789 > '{}'", old_fifo.display());
        let mut old_host = ChildGuard::spawn("old-order host", { let mut command = Command::new("sh"); command.arg("-c").arg(old_host_script); command }).unwrap();
        let old_start = Instant::now();
        while old_host.try_wait().unwrap().is_none() {
            assert!(old_start.elapsed() < Duration::from_secs(2));
            thread::sleep(Duration::from_millis(10));
        }
        old_compressor.kill_reap();
        assert!(!old_raw.exists() || fs::metadata(&old_raw).unwrap().len() == 0, "immediate compressor kill unexpectedly preserved delayed footer");
        let _ = fs::remove_dir_all(old_case);

        let case = dir("wall-limit");
        let fifo = case.join("host.raw.fifo");
        let raw = case.join("raw.trace.raw.gz");
        make_fifo(&fifo).unwrap();
        wall_limit_metadata(&case, 1);
        let script = format!("exec '{}' < '{}' > '{}'", delayed.display(), fifo.display(), raw.display());
        let mut compressor = ChildGuard::spawn("delayed gzip", { let mut command = Command::new("sh"); command.args(["-c", &script]); command }).unwrap();
        let host_script = format!("printf 0123456789 > '{}'", fifo.display());
        let mut host = ChildGuard::spawn("positive wall host", { let mut command = Command::new("sh"); command.arg("-c").arg(host_script); command }).unwrap();
        let result = wait_capture(&mut host, &mut compressor, &case, Duration::from_secs(3));
        assert!(result.unwrap_err().contains("capture metadata"));
        let raw_bytes = Command::new("gzip").args(["-dc", raw.to_str().unwrap()]).output().unwrap();
        assert!(raw_bytes.status.success());
        assert_eq!(raw_bytes.stdout, b"0123456789");
        let stage = fs::read_to_string(case.join("capture-stage1.json")).unwrap();
        assert!(stage.contains("positive_points_semantic_rejection"));
        assert!(stage.contains("raw_trace_bytes"));
        let _ = fs::remove_dir_all(case);
    }

    #[test]
    fn missing_or_zero_metadata_kills_blocked_compressor_promptly() {
        for (name, metadata) in [("missing", None), ("zero", Some("{\"points\":0}\n"))] {
            let case = dir(name);
            let fifo = case.join("host.raw.fifo");
            let raw = case.join("raw.trace.raw.gz");
            make_fifo(&fifo).unwrap();
            if let Some(contents) = metadata { fs::write(case.join("capture-metadata.json"), contents).unwrap(); }
            let script = format!("exec gzip -c < '{}' > '{}'", fifo.display(), raw.display());
            let mut compressor = ChildGuard::spawn("blocked gzip", { let mut command = Command::new("sh"); command.args(["-c", &script]); command }).unwrap();
            let mut host = ChildGuard::spawn("empty host", Command::new("true")).unwrap();
            let error = wait_capture(&mut host, &mut compressor, &case, Duration::from_secs(3)).unwrap_err();
            assert!(error.contains("capture metadata"));
            assert!(compressor.try_wait().unwrap().is_some());
            let stage = fs::read_to_string(case.join("capture-stage1.json")).unwrap();
            assert!(stage.contains("metadata_missing_or_zero_points"));
            assert!(!raw.exists() || fs::metadata(raw).unwrap().len() == 0);
            let _ = fs::remove_dir_all(case);
        }
    }
}

#[cfg(test)]
mod inherited_fd_tests {
    use super::*;
    use std::io::Write;

    fn pigz_path() -> PathBuf {
        PathBuf::from("/opt/homebrew/bin/pigz")
    }

    fn wait_bounded_child(child: &mut Child) -> ExitStatus {
        let start = Instant::now();
        loop {
            if let Some(status) = child.try_wait().unwrap() { return status; }
            assert!(start.elapsed() < Duration::from_secs(5), "fixture child exceeded bounded test wait");
            thread::sleep(Duration::from_millis(10));
        }
    }

    #[test]
    fn anonymous_stdin_pipe_reaches_eof_and_roundtrips() {
        let dir = env::temp_dir().join(format!("m07-native29-pipe-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let raw = dir.join("raw.gz");
        let payload = b"fault42-anonymous-pipe-eof\n".repeat(1024);
        let mut compressor = Command::new(pigz_path()).args(["-p", "4", "-c"])
            .stdin(Stdio::piped()).stdout(File::create(&raw).unwrap()).spawn().unwrap();
        let mut writer = compressor.stdin.take().unwrap();
        writer.write_all(&payload).unwrap();
        drop(writer);
        assert!(wait_bounded_child(&mut compressor).success());
        let decoded = Command::new("gzip").args(["-dc", raw.to_str().unwrap()]).output().unwrap();
        assert!(decoded.status.success());
        assert_eq!(decoded.stdout, payload);
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    #[ignore = "requires approved inherited-fd execution environment; sandbox returns EPERM"]
    fn dynamic_fd_host_roundtrip_requires_success() {
        let dir = env::temp_dir().join(format!("m07-native29-fd-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let raw = dir.join("raw.gz");
        let payload = b"dynamic-fd-fault-export\n";
        let mut compressor = Command::new(pigz_path()).args(["-p", "4", "-c"])
            .stdin(Stdio::piped()).stdout(File::create(&raw).unwrap()).spawn().unwrap();
        let writer = compressor.stdin.take().unwrap();
        let fd = writer.as_raw_fd();
        let export = format!("/dev/fd/{fd}");
        let mut host = Command::new("sh");
        host.args(["-c", "printf '%s\\n' \"$1\" > \"$2\"", "sh", "dynamic-fd-fault-export", &export]);
        install_export_fd(&mut host, fd);
        let mut host = host.spawn().unwrap();
        let status = wait_bounded_child(&mut host);
        drop(writer);
        assert!(status.success(), "inherited fd host failed: {status}");
        assert!(wait_bounded_child(&mut compressor).success());
        let decoded = Command::new("gzip").args(["-dc", raw.to_str().unwrap()]).output().unwrap();
        assert!(decoded.status.success());
        assert_eq!(decoded.stdout, payload);
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn dynamic_fd_host_start_failure_reaps_compressor() {
        let dir = env::temp_dir().join(format!("m07-native29-fail-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let raw = dir.join("raw.gz");
        let mut compressor = Command::new(pigz_path()).args(["-p", "4", "-c"])
            .stdin(Stdio::piped()).stdout(File::create(&raw).unwrap()).spawn().unwrap();
        let writer = compressor.stdin.take().unwrap();
        let fd = writer.as_raw_fd();
        let mut missing = Command::new("/definitely/missing/native-host");
        install_export_fd(&mut missing, fd);
        assert!(missing.spawn().is_err());
        drop(writer);
        assert!(wait_bounded_child(&mut compressor).success());
        let check = Command::new("gzip").args(["-t", raw.to_str().unwrap()]).status().unwrap();
        assert!(check.success());
        fs::remove_dir_all(dir).unwrap();
    }
}
