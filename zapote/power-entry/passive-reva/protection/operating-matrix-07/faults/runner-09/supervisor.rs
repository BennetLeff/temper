//! Bounded, single-case supervisor for the fault campaign transport.
//!
//! This owns the process lifecycle around one already-materialized case. It
//! intentionally does not launch a grid or make an engineering decision: the
//! maintained adapter and checker remain the authorities. The only retained
//! trace is raw.trace.tsv.gz; checked and supplemental streams are FIFOs.

use std::{
    env, fs,
    fs::File,
    os::unix::fs::FileTypeExt,
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

const USAGE: &str = "supervisor CASE TRACKER ADAPTER CHECKER PIGZ TSTOP ADAPTER_KIND CHECKER_KIND MUTATION_S EVENT_WINDOW OBSERVATION_S MAX_GAP WALL_SECONDS EXPORT_TIMEOUT";

struct ChildGuard {
    label: &'static str,
    child: Option<Child>,
}

impl ChildGuard {
    fn spawn(label: &'static str, mut command: Command) -> Result<Self, String> {
        let child = command.spawn().map_err(|e| format!("spawn {label}: {e}"))?;
        Ok(Self { label, child: Some(child) })
    }

    fn try_wait(&mut self) -> Result<Option<ExitStatus>, String> {
        self.child
            .as_mut()
            .ok_or_else(|| format!("{} already reaped", self.label))?
            .try_wait()
            .map_err(|e| format!("wait {}: {e}", self.label))
    }

    #[cfg(test)]
    fn wait_for(&mut self, timeout: Duration) -> Result<ExitStatus, String> {
        let start = Instant::now();
        loop {
            if let Some(status) = self.try_wait()? {
                return Ok(status);
            }
            if start.elapsed() >= timeout {
                self.kill_reap();
                return Err(format!("{} exceeded {:?}", self.label, timeout));
            }
            thread::sleep(Duration::from_millis(5));
        }
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

fn positive(name: &str, value: &str) -> Result<f64, String> {
    let value = value.parse::<f64>().map_err(|_| format!("invalid {name}"))?;
    if value.is_finite() && value > 0.0 {
        Ok(value)
    } else {
        Err(format!("{name} must be finite and positive"))
    }
}

fn require_file(path: &Path, label: &str) -> Result<(), String> {
    let meta = fs::metadata(path).map_err(|e| format!("{label} {}: {e}", path.display()))?;
    if !meta.is_file() {
        return Err(format!("{} is not a regular file: {}", label, path.display()));
    }
    Ok(())
}

fn make_fifo(path: &Path) -> Result<(), String> {
    if path.exists() {
        return Err(format!("refusing existing FIFO/output {}", path.display()));
    }
    let status = Command::new("mkfifo")
        .arg(path)
        .status()
        .map_err(|e| format!("mkfifo {}: {e}", path.display()))?;
    if !status.success() {
        return Err(format!("mkfifo failed for {}", path.display()));
    }
    let meta = fs::metadata(path).map_err(|e| format!("fifo metadata: {e}"))?;
    if !meta.file_type().is_fifo() {
        return Err(format!("{} is not a FIFO", path.display()));
    }
    Ok(())
}

fn sha256(path: &Path) -> Result<String, String> {
    let output = Command::new("shasum")
        .args(["-a", "256", path.to_str().ok_or("non-UTF8 hash path")?])
        .output()
        .map_err(|e| format!("hash {}: {e}", path.display()))?;
    if !output.status.success() {
        return Err(format!("hash failed for {}", path.display()));
    }
    String::from_utf8_lossy(&output.stdout)
        .split_whitespace()
        .next()
        .map(str::to_owned)
        .ok_or_else(|| format!("missing hash for {}", path.display()))
}

fn ensure_outputs_absent(case: &Path) -> Result<(), String> {
    const OUTPUTS: &[&str] = &[
        "source-identity.json", "raw.trace.tsv.gz", "raw-gzip.stderr", "host.stdout",
        "host.stderr", "first-invalid.tsv", "stage1.exit", "adapter.stdout",
        "adapter.stderr", "decode.stderr", "checker.stdout", "checker.stderr",
        "adapter-report.txt", "stage2.exit", "result.json", "host.raw.fifo",
        "adapter.raw.fifo", "checked.fifo", "progress.tsv", "stop.txt",
        "capture-metadata.json", "run-parameters.json",
    ];
    for name in OUTPUTS {
        if case.join(name).exists() {
            return Err(format!("refusing existing output {}", case.join(name).display()));
        }
    }
    Ok(())
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

fn include_token(line: &str) -> Result<Option<String>, String> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('*') || line.starts_with(';') { return Ok(None); }
    let mut fields = line.split_whitespace();
    let directive = fields.next().unwrap_or("");
    if directive.eq_ignore_ascii_case(".lib") || directive.eq_ignore_ascii_case(".inc") {
        return Err(format!("unsupported source directive: {line}"));
    }
    if !directive.eq_ignore_ascii_case(".include") { return Ok(None); }
    let token = fields.next().ok_or_else(|| format!("missing include path: {line}"))?;
    if fields.next().is_some() { return Err(format!("unsupported include syntax: {line}")); }
    let token = token.trim_matches(['\'', '"']);
    if token.is_empty() { return Err(format!("empty include path: {line}")); }
    Ok(Some(token.to_owned()))
}

fn input_files(root: &Path, path: &Path, seen: &mut Vec<PathBuf>) -> Result<(), String> {
    let root = fs::canonicalize(root).map_err(|e| format!("case root: {e}"))?;
    let canonical = fs::canonicalize(path).map_err(|e| format!("include {}: {e}", path.display()))?;
    if !canonical.starts_with(&root) { return Err(format!("include escapes case root: {}", canonical.display())); }
    if seen.iter().any(|existing| existing == &canonical) { return Ok(()); }
    if !canonical.is_file() { return Err(format!("include is not a file: {}", canonical.display())); }
    seen.push(canonical.clone());
    let bytes = fs::read(&canonical).map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&bytes);
    for line in text.lines() {
        if let Some(token) = include_token(line)? {
            input_files(&root, &canonical.parent().unwrap_or(&root).join(token), seen)?;
        }
    }
    Ok(())
}

fn source_listing(case: &Path) -> Result<Vec<(String, PathBuf, String)>, String> {
    let root = fs::canonicalize(case).map_err(|e| format!("case root: {e}"))?;
    let mut paths = Vec::new();
    input_files(&root, &root.join("case.cir"), &mut paths)?;
    let manifest = root.join("manifest.json");
    require_file(&manifest, "case manifest")?;
    paths.push(fs::canonicalize(manifest).map_err(|e| e.to_string())?);
    paths.sort(); paths.dedup();
    paths.into_iter().map(|path| {
        let relative = path.strip_prefix(&root).map_err(|e| e.to_string())?.to_string_lossy().into_owned();
        Ok((relative, path.clone(), sha256(&path)?))
    }).collect()
}

fn write_identity(case: &Path, tracker: &Path, adapter: &Path, checker: &Path, pigz: &Path) -> Result<(), String> {
    let files = source_listing(case)?;
    let mut input_json = String::new();
    for (index, (relative, _, hash)) in files.iter().enumerate() {
        if index > 0 { input_json.push_str(",\n"); }
        input_json.push_str(&format!("    {{\"path\": \"{}\", \"sha256\": \"{}\"}}", json_escape(relative), hash));
    }
    let text = format!(
        "{{\n  \"case_dir\": \"{}\",\n  \"input_files\": [\n{}\n  ],\n  \"tracker\": {{\"path\": \"{}\", \"sha256\": \"{}\"}},\n  \"adapter\": {{\"path\": \"{}\", \"sha256\": \"{}\"}},\n  \"checker\": {{\"path\": \"{}\", \"sha256\": \"{}\"}},\n  \"pigz\": {{\"path\": \"{}\", \"sha256\": \"{}\"}}\n}}\n",
        json_escape(&case.display().to_string()), input_json, json_escape(&tracker.display().to_string()), sha256(tracker)?,
        json_escape(&adapter.display().to_string()), sha256(adapter)?, json_escape(&checker.display().to_string()), sha256(checker)?, json_escape(&pigz.display().to_string()), sha256(pigz)?
    );
    fs::write(case.join("source-identity.json"), text).map_err(|e| e.to_string())
}

fn write_failure(case: &Path, classification: &str, detail: &str) {
    let text = format!(
        "{{\n  \"classification\": \"{}\",\n  \"detail\": \"{}\",\n  \"transport_complete\": false\n}}\n",
        json_escape(classification), json_escape(detail)
    );
    let _ = fs::write(case.join("result.json"), text);
}

fn write_parameters(case: &Path, args: &[String], tstop: f64, mutation: f64, event_window: f64, observation: f64, max_gap: f64, wall: f64, export_timeout: f64) -> Result<(), String> {
    let values: Vec<String> = args.iter().skip(6).map(|value| format!("\"{}\"", json_escape(value))).collect();
    let text = format!(
        "{{\n  \"tstop_s\": {:.17e},\n  \"adapter_kind\": \"{}\",\n  \"checker_kind\": \"{}\",\n  \"mutation_s\": {:.17e},\n  \"event_window_s\": {:.17e},\n  \"observation_s\": {:.17e},\n  \"max_gap_s\": {:.17e},\n  \"wall_seconds\": {:.17e},\n  \"export_timeout_s\": {:.17e},\n  \"argv_tail\": [{}]\n}}\n",
        tstop, json_escape(&args[7]), json_escape(&args[8]), mutation, event_window,
        observation, max_gap, wall, export_timeout, values.join(", ")
    );
    fs::write(case.join("run-parameters.json"), text).map_err(|e| e.to_string())
}

fn log_file(case: &Path, name: &str) -> Result<File, String> {
    File::create(case.join(name)).map_err(|e| format!("create {name}: {e}"))
}

fn shell_quote(path: &Path) -> Result<String, String> {
    let value = path.to_str().ok_or("non-UTF8 path")?;
    Ok(format!("'{}'", value.replace('\'', "'\\''")))
}

fn spawn_tracker(
    case: &Path,
    tracker: &Path,
    wall: f64,
    tstop: f64,
    fifo: &Path,
) -> Result<ChildGuard, String> {
    let stdout = log_file(case, "host.stdout")?;
    let stderr = log_file(case, "host.stderr")?;
    let mut command = Command::new(tracker);
    command
        .current_dir(case)
        .args([
            "case.cir",
            &format!("{wall:.12}"),
            &format!("{tstop:.12}"),
            fifo.to_str().ok_or("FIFO path")?,
            "first-invalid.tsv",
        ])
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    ChildGuard::spawn("tracked host", command)
}

fn wait_pair(first: &mut ChildGuard, second: &mut ChildGuard, timeout: Duration) -> Result<(ExitStatus, ExitStatus), String> {
    let start = Instant::now();
    let mut first_status = None;
    let mut second_status = None;
    loop {
        if first_status.is_none() { first_status = first.try_wait()?; }
        if second_status.is_none() { second_status = second.try_wait()?; }
        if let Some(status) = first_status {
            if !status.success() && second_status.is_none() {
                second.kill_reap();
                return Err(format!("{} failed: {status}", first.label));
            }
        }
        if let Some(status) = second_status {
            if !status.success() && first_status.is_none() {
                first.kill_reap();
                return Err(format!("{} failed: {status}", second.label));
            }
        }
        if let (Some(one), Some(two)) = (first_status, second_status) { return Ok((one, two)); }
        if start.elapsed() >= timeout {
            first.kill_reap();
            second.kill_reap();
            return Err("stage1 children exceeded bounded timeout".into());
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn wait_pipeline(adapter: &mut ChildGuard, decoder: &mut ChildGuard, checker: &mut ChildGuard, checker_log: &Path, timeout: Duration) -> Result<(ExitStatus, ExitStatus, ExitStatus), String> {
    let start = Instant::now();
    let mut adapter_status = None;
    let mut decoder_status = None;
    let mut checker_status = None;
    loop {
        if adapter_status.is_none() { adapter_status = adapter.try_wait()?; }
        if decoder_status.is_none() { decoder_status = decoder.try_wait()?; }
        if checker_status.is_none() { checker_status = checker.try_wait()?; }
        if let Some(status) = adapter_status {
            if !status.success() {
                decoder.kill_reap(); checker.kill_reap();
                return Err(format!("adapter rejected trace: {status}"));
            }
        }
        if let Some(status) = decoder_status {
            if !status.success() {
                adapter.kill_reap(); checker.kill_reap();
                return Err(format!("raw decoder failed: {status}"));
            }
        }
        if let Some(status) = checker_status {
            if !status.success() && (adapter_status.is_none() || decoder_status.is_none()) {
                // A completed categorical result may become observable before
                // the upstream processes are reaped. Still require both to
                // finish successfully within the deadline before recording it.
                let declared_gap = fs::read_to_string(checker_log)
                    .map(|text| text.contains("PROTECTION_GAP")).unwrap_or(false);
                if !declared_gap {
                    adapter.kill_reap(); decoder.kill_reap();
                    return Err(format!("checker exited before pipeline completed: {status}"));
                }
            }
        }
        if let (Some(a), Some(d), Some(c)) = (adapter_status, decoder_status, checker_status) { return Ok((a, d, c)); }
        if start.elapsed() >= timeout {
            adapter.kill_reap(); decoder.kill_reap(); checker.kill_reap();
            return Err("pipeline children exceeded bounded timeout".into());
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn run_case(args: &[String]) -> Result<(), String> {
    if args.len() != 15 {
        return Err(format!("usage: {USAGE}"));
    }
    let case = fs::canonicalize(&args[1]).map_err(|e| format!("case: {e}"))?;
    let tool = |index: usize, label: &str| -> Result<PathBuf, String> {
        fs::canonicalize(&args[index]).map_err(|e| {
            let detail = format!("{label} {}: {e}", args[index]);
            if !case.join("result.json").exists() { write_failure(&case, "missing_executable", &detail); }
            detail
        })
    };
    let tracker = tool(2, "tracker")?;
    let adapter = tool(3, "adapter")?;
    let checker = tool(4, "checker")?;
    let pigz = tool(5, "pigz")?;
    for (path, label) in [
        (&tracker, "tracker"),
        (&adapter, "adapter"),
        (&checker, "checker"),
        (&pigz, "pigz"),
    ] {
        require_file(path, label)?;
    }
    let tstop = positive("TSTOP", &args[6])?;
    let mutation = positive("MUTATION_S", &args[9])?;
    let event_window = positive("EVENT_WINDOW", &args[10])?;
    let observation = positive("OBSERVATION_S", &args[11])?;
    let max_gap = positive("MAX_GAP", &args[12])?;
    let wall = positive("WALL_SECONDS", &args[13])?;
    let export_timeout = positive("EXPORT_TIMEOUT", &args[14])?;
    require_file(&case.join("case.cir"), "case deck")?;
    ensure_outputs_absent(&case)?;
    let source_before = source_listing(&case)?;
    write_identity(&case, &tracker, &adapter, &checker, &pigz)?;
    write_parameters(&case, args, tstop, mutation, event_window, observation, max_gap, wall, export_timeout)?;
    let raw_fifo = case.join("host.raw.fifo");
    let adapter_fifo = case.join("adapter.raw.fifo");
    let checked_fifo = case.join("checked.fifo");
    let raw_gz = case.join("raw.trace.tsv.gz");
    let mut created_fifos: Vec<PathBuf> = Vec::new();
    for path in [&raw_fifo, &adapter_fifo, &checked_fifo] {
        if let Err(error) = make_fifo(path) {
            for created in &created_fifos { let _ = fs::remove_file(created); }
            return Err(error);
        }
        created_fifos.push(path.to_path_buf());
    }

    let result = (|| {
        // Let the shell open the FIFO read-only. Opening it read-write in the
        // compressor would retain a writer in that child and suppress EOF.
        let compressor_script = format!(
            "exec {} -p 4 -c < {} > {}",
            shell_quote(&pigz)?, shell_quote(&raw_fifo)?, shell_quote(&raw_gz)?
        );
        let mut compressor_cmd = Command::new("sh");
        compressor_cmd
            .current_dir(&case)
            .args(["-c", &compressor_script])
            .stderr(Stdio::from(log_file(&case, "raw-gzip.stderr")?));
        let mut compressor = ChildGuard::spawn("raw compressor", compressor_cmd)?;
        let mut tracker_child = spawn_tracker(&case, &tracker, wall, tstop, &raw_fifo)?;
        let (host_status, gzip_status) = match wait_pair(
            &mut tracker_child,
            &mut compressor,
            Duration::from_secs_f64(wall + export_timeout + 5.0),
        ) {
            Ok(statuses) => statuses,
            Err(error) => { write_failure(&case, "stage1_transport_failure", &error); return Err(error); }
        };
        fs::write(
            case.join("stage1.exit"),
            format!(
                "host_rc={} host_success={} gzip_rc={} gzip_success={}\n",
                host_status.code().unwrap_or(-1),
                host_status.success(),
                gzip_status.code().unwrap_or(-1),
                gzip_status.success()
            ),
        )
        .map_err(|e| e.to_string())?;
        if !host_status.success() {
            return Err(format!("tracked host failed: {host_status}"));
        }
        if !gzip_status.success() {
            return Err(format!("raw compressor failed: {gzip_status}"));
        }

        let mut checker_cmd = Command::new(&checker);
        checker_cmd
            .current_dir(&case)
            .args([
                checked_fifo.to_str().ok_or("checked FIFO path")?,
                &format!("{tstop:.12}"),
                &args[8],
                &format!("{mutation:.12}"),
                &format!("{event_window:.12}"),
                "2e-6",
                &format!("{observation:.12}"),
                &format!("{max_gap:.12}"),
            ])
            .stdout(Stdio::from(log_file(&case, "checker.stdout")?))
            .stderr(Stdio::from(log_file(&case, "checker.stderr")?));
        let mut checker_child = ChildGuard::spawn("fault checker", checker_cmd)?;

        let mut adapter_cmd = Command::new(&adapter);
        adapter_cmd
            .current_dir(&case)
            .args([
                adapter_fifo.to_str().ok_or("adapter FIFO path")?,
                checked_fifo.to_str().ok_or("checked FIFO path")?,
                "/dev/null",
                "adapter-report.txt",
                &format!("{tstop:.12}"),
                &args[7],
                &format!("{mutation:.12}"),
                &format!("{event_window:.12}"),
                &format!("{max_gap:.12}"),
            ])
            .stdout(Stdio::from(log_file(&case, "adapter.stdout")?))
            .stderr(Stdio::from(log_file(&case, "adapter.stderr")?));
        let mut adapter_child = ChildGuard::spawn("fault adapter", adapter_cmd)?;

        let decoder_script = format!(
            "exec gzip -cd {} > {}",
            shell_quote(&raw_gz)?, shell_quote(&adapter_fifo)?
        );
        let mut decoder_cmd = Command::new("sh");
        decoder_cmd
            .current_dir(&case)
            .args(["-c", &decoder_script])
            .stderr(Stdio::from(log_file(&case, "decode.stderr")?));
        let mut decoder = ChildGuard::spawn("raw decoder", decoder_cmd)?;

        let (adapter_status, decoder_status, checker_status) = match wait_pipeline(
            &mut adapter_child,
            &mut decoder,
            &mut checker_child,
            &case.join("checker.stderr"),
            Duration::from_secs_f64(export_timeout),
        ) {
            Ok(statuses) => statuses,
            Err(error) => { write_failure(&case, "stage2_transport_failure", &error); return Err(error); }
        };
        let source_after = source_listing(&case)?;
        if source_before != source_after {
            let error = "source/include closure changed during transport";
            write_failure(&case, "source_mutated_during_run", error);
            return Err(error.into());
        }
        fs::write(
            case.join("stage2.exit"),
            format!(
                "adapter_rc={} adapter_success={} decoder_rc={} decoder_success={} checker_rc={} checker_success={}\n",
                adapter_status.code().unwrap_or(-1),
                adapter_status.success(),
                decoder_status.code().unwrap_or(-1),
                decoder_status.success(),
                checker_status.code().unwrap_or(-1),
                checker_status.success()
            ),
        )
        .map_err(|e| e.to_string())?;
        let checker_stderr = fs::read_to_string(case.join("checker.stderr")).unwrap_or_default();
        let classification = if checker_status.success() {
            "checker_pass"
        } else if checker_stderr.contains("PROTECTION_GAP") {
            "expected_checker_protection_gap"
        } else {
            "checker_rejected_or_parse_failure"
        };
        fs::write(
            case.join("result.json"),
            format!(
                "{{\n  \"classification\": \"{classification}\",\n  \"checker_success\": {},\n  \"transport_complete\": true,\n  \"raw_trace\": \"raw.trace.tsv.gz\",\n  \"raw_trace_sha256\": \"{}\",\n  \"supplemental\": \"not-retained; raw trace is authoritative\",\n  \"tstop_s\": {tstop:.17e},\n  \"mutation_s\": {mutation:.17e},\n  \"event_window_s\": {event_window:.17e},\n  \"observation_s\": {observation:.17e},\n  \"max_gap_s\": {max_gap:.17e}\n}}\n",
                checker_status.success(), sha256(&raw_gz)?
            ),
        )
        .map_err(|e| e.to_string())?;
        if checker_status.success() || checker_stderr.contains("PROTECTION_GAP") {
            Ok(())
        } else {
            Err("checker did not produce a pass or declared PROTECTION_GAP".into())
        }
    })();
    if let Err(error) = &result {
        if !case.join("result.json").exists() {
            write_failure(&case, "supervisor_failure", error);
        }
    }
    for path in [&raw_fifo, &adapter_fifo, &checked_fifo] {
        let _ = fs::remove_file(path);
    }
    result
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if let Err(error) = run_case(&args) {
        eprintln!("SUPERVISOR_REJECTED {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn positive_rejects_nan_zero_and_negative() {
        assert!(positive("x", "1e-6").is_ok());
        assert!(positive("x", "0").is_err());
        assert!(positive("x", "-1").is_err());
        assert!(positive("x", "NaN").is_err());
    }

    #[test]
    fn child_guard_reaps_failed_child() {
        let mut command = Command::new("sh");
        command.args(["-c", "exit 17"]);
        let mut child = ChildGuard::spawn("fixture", command).unwrap();
        let status = child.wait_for(Duration::from_secs(1)).unwrap();
        assert_eq!(status.code(), Some(17));
    }

    #[test]
    fn fifo_is_real_fifo() {
        let dir = std::env::temp_dir().join(format!("matrix07-supervisor-{}", std::process::id()));
        let _ = fs::create_dir_all(&dir);
        let path = dir.join("fixture.fifo");
        make_fifo(&path).unwrap();
        assert!(fs::metadata(&path).unwrap().file_type().is_fifo());
        let _ = fs::remove_file(path);
        let _ = fs::remove_dir(dir);
    }

    #[test]
    fn include_escape_is_rejected_and_json_controls_are_escaped() {
        let parent = std::env::temp_dir().join(format!("matrix07-supervisor-escape-{}", std::process::id()));
        let case = parent.join("case");
        fs::create_dir_all(&case).unwrap();
        fs::write(case.join("case.cir"), ".include ../outside.inc\n").unwrap();
        fs::write(case.join("manifest.json"), "{}\n").unwrap();
        fs::write(parent.join("outside.inc"), "* outside\n").unwrap();
        assert!(source_listing(&case).is_err());
        assert_eq!(json_escape("a\t\r\n\u{0001}\""), "a\\t\\r\\n\\u0001\\\"");
        assert_eq!(json_escape("México"), "México");
        let _ = fs::remove_dir_all(parent);
    }

    #[test]
    fn unsupported_include_forms_fail_closed() {
        assert_eq!(include_token(".include part.inc").unwrap(), Some("part.inc".into()));
        assert!(include_token(".include outside.inc ; comment").is_err());
        assert!(include_token(".include").is_err());
        assert!(include_token(".inc part.inc").is_err());
        assert!(include_token(".lib part.lib section").is_err());
    }

    #[test]
    fn categorical_gap_waits_for_upstream_reaping() {
        let dir = env::temp_dir().join(format!("matrix07-gap-race-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let log = dir.join("checker.stderr");
        let sleeper = || {
            let mut command = Command::new("/bin/sleep");
            command.arg("0.1");
            ChildGuard::spawn("fixture upstream", command).unwrap()
        };
        let mut adapter = sleeper();
        let mut decoder = sleeper();
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "echo PROTECTION_GAP >&2; exit 1"])
            .stderr(Stdio::from(File::create(&log).unwrap()));
        let mut checker = ChildGuard::spawn("fixture checker", command).unwrap();
        let (a, d, c) = wait_pipeline(&mut adapter, &mut decoder, &mut checker, &log, Duration::from_secs(2)).unwrap();
        assert!(a.success() && d.success());
        assert_eq!(c.code(), Some(1));
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn ordinary_early_checker_failure_reaps_upstream_promptly() {
        let sleeper = || {
            let mut command = Command::new("/bin/sleep");
            command.arg("10");
            ChildGuard::spawn("fixture upstream", command).unwrap()
        };
        let mut adapter = sleeper();
        let mut decoder = sleeper();
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "exit 23"]);
        let mut checker = ChildGuard::spawn("fixture checker", command).unwrap();
        let start = Instant::now();
        assert!(wait_pipeline(&mut adapter, &mut decoder, &mut checker, Path::new("/nonexistent-checker-log"), Duration::from_secs(2)).is_err());
        assert!(start.elapsed() < Duration::from_secs(1));
        assert!(adapter.try_wait().unwrap().is_some());
        assert!(decoder.try_wait().unwrap().is_some());
    }
}
