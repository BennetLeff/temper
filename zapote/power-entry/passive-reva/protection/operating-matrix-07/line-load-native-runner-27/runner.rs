//! Bounded, fail-closed line/load orchestration for matrix-07.
//!
//! This binary is intentionally an orchestrator.  It does not calculate an
//! engineering limit or reinterpret the operating-point checker.  It binds
//! each generated deck to an accepted cold-source receipt, runs at most two
//! independent tracked ngspice hosts, and forwards native raw traces through
//! a dedicated anonymous pipe (host-owned `/dev/fd/N`), then the native decoder, maintained
//! normalizer, diagnostic metrics, and checker.

use std::collections::VecDeque;
use std::env;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use std::iter::Skip;
#[cfg(unix)]
use std::os::unix::fs::FileTypeExt;
#[cfg(unix)]
use std::os::unix::io::{AsRawFd, RawFd};
#[cfg(unix)]
use std::os::unix::process::CommandExt;

#[cfg(unix)]
extern "C" { fn fcntl(fd: i32, cmd: i32, ...) -> i32; }

#[cfg(unix)]
#[cfg(unix)]
const F_GETFD: i32 = 1;
#[cfg(unix)]
const F_SETFD: i32 = 2;
#[cfg(unix)]
const FD_CLOEXEC: i32 = 1;

const MAX_WORKERS: usize = 2;
const DEFAULT_WORKERS: usize = 2;
const DEFAULT_WALL_LIMIT: u64 = 3600;
const DEFAULT_END_S: f64 = 0.65;

#[derive(Debug, Clone)]
struct Point {
    id: String,
    line_v: f64,
    rload: f64,
}

#[derive(Debug, Clone)]
struct Config {
    source_dir: PathBuf,
    baseline: PathBuf,
    manifest: PathBuf,
    output: PathBuf,
    tracked: PathBuf,
    normalize: PathBuf,
    checker: PathBuf,
    decoder: PathBuf,
    event_metrics: PathBuf,
    event_audit: PathBuf,
    spice_scripts: Option<PathBuf>,
    pigz: Option<PathBuf>,
    workers: usize,
    wall_limit: u64,
    end_s: f64,
    first_invalid_snapshot: bool,
    selected_cases: Option<Vec<String>>,
    self_test: bool,
    inspect: bool,
}

#[derive(Debug, Clone)]
struct Compressor {
    path: PathBuf,
    pigz: bool,
    threads: usize,
}

fn resolve_executable(name: &Path) -> Result<PathBuf, String> {
    let direct = name.is_absolute() || name.components().count() > 1;
    if direct {
        let canonical = fs::canonicalize(name).map_err(|e| format!("compressor {}: {e}", name.display()))?;
        if !canonical.is_file() { return err(format!("compressor is not a file: {}", canonical.display())); }
        return Ok(canonical);
    }
    let path = env::var_os("PATH").ok_or("PATH is unset; cannot resolve compressor")?;
    for dir in env::split_paths(&path) {
        let candidate = dir.join(name);
        if candidate.is_file() {
            let canonical = fs::canonicalize(&candidate).map_err(|e| format!("compressor {}: {e}", candidate.display()))?;
            if !canonical.is_file() { return err(format!("compressor is not a file: {}", canonical.display())); }
            return Ok(canonical);
        }
    }
    err(format!("compressor executable not found: {}", name.display()))
}

fn compressor_for(pigz: Option<&Path>) -> Result<Compressor, String> {
    let (requested, use_pigz, threads) = match pigz {
        Some(path) => (path, true, 4),
        None => (Path::new("gzip"), false, 1),
    };
    Ok(Compressor { path: resolve_executable(requested)?, pigz: use_pigz, threads })
}

#[derive(Debug)]
struct Running {
    point: Point,
    dir: PathBuf,
    child: Child,
    compressor: Child,
    started: Instant,
    last_progress: String,
}

impl Drop for Running {
    fn drop(&mut self) {
        // Best-effort containment for every early-return path: a failed
        // materialization, missing executable, or checker error must not leave
        // a FIFO reader or ngspice worker behind.
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = self.compressor.kill();
        let _ = self.compressor.wait();
    }
}

fn usage() -> &'static str {
    "usage: line-load-native-runner --source DIR --baseline acceptance.json --manifest manifest.json \
     --output DIR --tracked /path/matrix07-tracked --normalize /path/matrix07-normalize \
     --checker /path/matrix07-checker --decoder /path/native_stream_adapter \
     --event-metrics /path/event-metrics --event-audit /path/raw15-audit \
     [--spice-scripts DIR] [--workers 1..2] \
     [--wall-limit SEC] [--end-s SECONDS] [--pigz PATH] [--cases LL01,LL02]\n\
     or: line-load-runner --self-test"
}

fn err<T>(msg: impl Into<String>) -> Result<T, String> { Err(msg.into()) }

fn parse_args() -> Result<Config, String> {
    let mut args = env::args().skip(1).peekable();
    let mut c = Config {
        source_dir: PathBuf::new(), baseline: PathBuf::new(), manifest: PathBuf::new(),
        output: PathBuf::new(), tracked: PathBuf::new(), normalize: PathBuf::new(),
        checker: PathBuf::new(), decoder: PathBuf::new(), event_metrics: PathBuf::new(), event_audit: PathBuf::new(), spice_scripts: None, pigz: None, workers: DEFAULT_WORKERS,
        wall_limit: DEFAULT_WALL_LIMIT, end_s: DEFAULT_END_S, first_invalid_snapshot: false,
        selected_cases: None, self_test: false, inspect: false,
    };
    while let Some(arg) = args.next() {
        let value = |name: &str, args: &mut std::iter::Peekable<Skip<std::env::Args>>| {
            args.next().ok_or_else(|| format!("{name} requires a value"))
        };
        match arg.as_str() {
            "--self-test" => c.self_test = true,
            "--inspect" => c.inspect = true,
            "--source" => c.source_dir = PathBuf::from(value("--source", &mut args)?),
            "--baseline" => c.baseline = PathBuf::from(value("--baseline", &mut args)?),
            "--manifest" => c.manifest = PathBuf::from(value("--manifest", &mut args)?),
            "--output" => c.output = PathBuf::from(value("--output", &mut args)?),
            "--tracked" => c.tracked = PathBuf::from(value("--tracked", &mut args)?),
            "--normalize" => c.normalize = PathBuf::from(value("--normalize", &mut args)?),
            "--checker" => c.checker = PathBuf::from(value("--checker", &mut args)?),
            "--decoder" => c.decoder = PathBuf::from(value("--decoder", &mut args)?),
            "--event-metrics" => c.event_metrics = PathBuf::from(value("--event-metrics", &mut args)?),
            "--event-audit" => c.event_audit = PathBuf::from(value("--event-audit", &mut args)?),
            "--spice-scripts" => c.spice_scripts = Some(PathBuf::from(value("--spice-scripts", &mut args)?)),
            "--pigz" => c.pigz = Some(PathBuf::from(value("--pigz", &mut args)?)),
            "--workers" => c.workers = value("--workers", &mut args)?.parse().map_err(|_| "invalid --workers".to_string())?,
            "--wall-limit" => c.wall_limit = value("--wall-limit", &mut args)?.parse().map_err(|_| "invalid --wall-limit".to_string())?,
            "--end-s" => c.end_s = value("--end-s", &mut args)?.parse().map_err(|_| "invalid --end-s".to_string())?,
            "--first-invalid-snapshot" => c.first_invalid_snapshot = true,
            "--cases" => {
                let raw = value("--cases", &mut args)?;
                if raw.is_empty() { return err("--cases requires at least one case ID"); }
                let mut ids = Vec::new();
                for id in raw.split(',') {
                    if id.is_empty() || id.chars().any(char::is_whitespace) { return err("--cases contains an empty/whitespace ID"); }
                    if !matches!(id, "LL01" | "LL02" | "LL03" | "LL04" | "LL05" | "LL06" | "LL07" | "LL08" | "LL09") { return err(format!("unknown --cases ID {id}")); }
                    if ids.iter().any(|seen: &String| seen == id) { return err(format!("duplicate --cases ID {id}")); }
                    ids.push(id.to_string());
                }
                c.selected_cases = Some(ids);
            }
            "-h" | "--help" => return err(usage()),
            other => return err(format!("unknown argument {other}\n{usage}", usage = usage())),
        }
    }
    if c.self_test { return Ok(c); }
    if c.workers == 0 || c.workers > MAX_WORKERS { return err("--workers must be between 1 and 2"); }
    if c.wall_limit == 0 || !c.end_s.is_finite() || c.end_s <= 0.0 { return err("positive wall limit and end time required"); }
    for (name, p) in [("--source", &c.source_dir), ("--baseline", &c.baseline),
                      ("--manifest", &c.manifest), ("--output", &c.output),
                      ("--tracked", &c.tracked), ("--normalize", &c.normalize),
                      ("--checker", &c.checker), ("--decoder", &c.decoder),
                      ("--event-metrics", &c.event_metrics), ("--event-audit", &c.event_audit)] {
        if p.as_os_str().is_empty() { return err(format!("missing {name}")); }
    }
    Ok(c)
}

fn read_text(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))
}

fn jq(path: &Path, filter: &str) -> Result<String, String> {
    let out = Command::new("jq").args(["-e", "-r", filter, path.to_str().ok_or("invalid JSON path")?])
        .output().map_err(|e| format!("jq unavailable: {e}"))?;
    if !out.status.success() { return err(format!("jq rejected {}: {}", path.display(), String::from_utf8_lossy(&out.stderr).trim())); }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

fn json_key_count(text: &str, key: &str) -> usize {
    let needle = format!("\"{key}\"");
    text.match_indices(&needle).filter(|(i, _)| text[*i + needle.len()..].trim_start().starts_with(':')).count()
}

fn hash_bytes(bytes: &[u8]) -> Result<String, String> {
    let mut child = Command::new("shasum").args(["-a", "256"]).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn()
        .map_err(|e| format!("cannot start shasum: {e}"))?;
    child.stdin.take().ok_or("shasum stdin unavailable")?.write_all(bytes).map_err(|e| e.to_string())?;
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    if !out.status.success() { return err(format!("shasum failed: {}", String::from_utf8_lossy(&out.stderr))); }
    String::from_utf8_lossy(&out.stdout).split_whitespace().next().map(str::to_string).ok_or_else(|| "empty shasum output".to_string())
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let output = Command::new("shasum").args(["-a", "256", path.to_str().ok_or("invalid hash path")?]).output().map_err(|e| format!("shasum {}: {e}", path.display()))?;
    if !output.status.success() { return err(format!("shasum {} failed", path.display())); }
    String::from_utf8_lossy(&output.stdout).split_whitespace().next().map(str::to_owned).ok_or_else(|| format!("shasum {} returned no digest", path.display()))
}

fn parse_include_lines(text: &str) -> Result<Vec<String>, String> {
    let mut names = Vec::new();
    for line in text.lines() {
        let t = line.trim();
        let Some(rest) = t.get(..8).filter(|prefix| prefix.eq_ignore_ascii_case(".include")).map(|_| &t[8..]) else {
            if t.get(..4).is_some_and(|prefix| prefix.eq_ignore_ascii_case(".inc")) || t.get(..4).is_some_and(|prefix| prefix.eq_ignore_ascii_case(".lib")) { return err(format!("unsupported include directive {t}")); }
            continue;
        };
        if !rest.is_empty() && !rest.chars().next().is_some_and(char::is_whitespace) { return err(format!("unsupported include directive {t}")); }
        let mut fields = rest.split_whitespace();
        let name = fields.next().ok_or("empty .include")?;
        if fields.next().is_some() { return err(format!("unsupported extra tokens in include {t}")); }
        if name.starts_with('"') || name.starts_with('\'') || name.contains('\\') { return err(format!("unsupported quoted/backslash include {name}")); }
        names.push(name.to_string());
    }
    Ok(names)
}

fn include_names(source: &Path) -> Result<Vec<String>, String> {
    let root = fs::canonicalize(source).map_err(|e| format!("source root: {e}"))?;
    let deck = root.join("cold.cir");
    let mut seen = Vec::new();
    let mut stack = Vec::new();
    fn visit(path: &Path, root: &Path, seen: &mut Vec<String>, stack: &mut Vec<PathBuf>) -> Result<(), String> {
        let rel_lex = path.strip_prefix(root).map_err(|_| "include escapes source root")?;
        let mut cursor = root.to_path_buf();
        for component in rel_lex.components() {
            if let std::path::Component::Normal(part) = component {
                cursor.push(part);
                if fs::symlink_metadata(&cursor).map_err(|e| e.to_string())?.file_type().is_symlink() { return err(format!("include symlink alias rejected: {}", path.display())); }
            }
        }
        let canonical = fs::canonicalize(path).map_err(|e| format!("include {}: {e}", path.display()))?;
        if !canonical.starts_with(root) { return err(format!("include escapes source root: {}", path.display())); }
        if stack.contains(&canonical) { return err(format!("include cycle at {}", path.display())); }
        let rel = canonical.strip_prefix(root).map_err(|_| "include root mismatch")?.to_string_lossy().replace('\\', "/");
        if seen.iter().any(|x| x == &rel) { return Ok(()); }
        stack.push(canonical.clone());
        let bytes = fs::read(&canonical).map_err(|e| format!("include {}: {e}", canonical.display()))?;
        // Vendor comments may contain non-UTF8 bytes. Parse their ASCII include
        // directives through a lossy text view; hash and copy the original bytes.
        let nested = parse_include_lines(&String::from_utf8_lossy(&bytes))?;
        for name in nested {
            let rel_path = Path::new(&name);
            if rel_path.is_absolute() || rel_path.components().any(|c| matches!(c, std::path::Component::ParentDir)) { return err(format!("unsafe include path {name}")); }
            let child = canonical.parent().ok_or("include has no parent")?.join(rel_path);
            visit(&child, root, seen, stack)?;
        }
        stack.pop();
        if rel != "cold.cir" { seen.push(rel); }
        Ok(())
    }
    visit(&deck, &root, &mut seen, &mut stack)?;
    seen.sort();
    if seen.is_empty() { return err("deck has no includes"); }
    Ok(seen)
}

fn include_digest(source: &Path, names: &[String]) -> Result<String, String> {
    let mut material = Vec::new();
    for n in names {
        let p = source.join(n);
        let h = sha256_file(&p)?;
        material.extend_from_slice(n.as_bytes()); material.push(0); material.extend_from_slice(h.as_bytes()); material.push(b'\n');
    }
    hash_bytes(&material)
}

fn parse_points(path: &Path) -> Result<Vec<Point>, String> {
    let filter = r#"
      if (.points|type) != "array" or (.points|length) != 9 then error("points must contain exactly nine rows") end |
      .points as $p |
      if ([$p[].id]|sort) != ["LL01","LL02","LL03","LL04","LL05","LL06","LL07","LL08","LL09"] then error("IDs must be exactly LL01..LL09") end |
      if any($p[]; (type != "object") or ((.id|type)!="string") or ((.status|type)!="string") or (.status!="planned_unexecuted") or ((.line_v_rms|type)!="number") or ((.line_v_rms|isfinite|not)) or (.line_v_rms<=0) or ((.rload_ohm|type)!="number") or ((.rload_ohm|isfinite|not)) or (.rload_ohm<=0)) then error("invalid point row") end |
      .points[] | [.id,.line_v_rms,.rload_ohm] | @tsv
    "#;
    let rows = jq(path, filter)?;
    let mut out = Vec::new();
    for line in rows.lines() {
        let mut f = line.split('\t');
        let id = f.next().ok_or("jq point id missing")?.to_string();
        let line_v = f.next().ok_or("jq line voltage missing")?.parse().map_err(|_| "jq line voltage invalid")?;
        let rload = f.next().ok_or("jq load missing")?.parse().map_err(|_| "jq load invalid")?;
        out.push(Point { id, line_v, rload });
    }
    if out.len() != 9 { return err("jq returned fewer than nine points"); }
    Ok(out)
}

fn select_points(points: Vec<Point>, selected: Option<&[String]>) -> Result<Vec<Point>, String> {
    let Some(selected) = selected else { return Ok(points); };
    if selected.is_empty() { return err("case selection cannot be empty"); }
    for (index, id) in selected.iter().enumerate() {
        if selected[..index].iter().any(|previous| previous == id) { return err(format!("duplicate selected case {id}")); }
    }
    let mut out = Vec::new();
    // Iterate the already validated manifest order so a user-provided order
    // cannot silently reorder the staged run or its receipts.
    for point in points {
        if selected.iter().any(|id| id == &point.id) { out.push(point); }
    }
    if out.len() != selected.len() { return err("selected case ID is not present in the validated manifest"); }
    Ok(out)
}

fn json_string_array(values: &[String]) -> String {
    let mut out = String::from("[");
    for (index, value) in values.iter().enumerate() {
        if index != 0 { out.push_str(", "); }
        out.push('"'); out.push_str(value); out.push('"');
    }
    out.push(']');
    out
}

fn json_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"").replace('\n', "\\n").replace('\r', "\\r").replace('\t', "\\t")
}

fn replace_param(line: &str, key: &str, value: &str) -> Result<String, String> {
    let prefix = format!("{key}=");
    let positions: Vec<_> = line.match_indices(&prefix).filter_map(|(i, _)| {
        if i == 0 || line[..i].chars().last().is_some_and(char::is_whitespace) { Some(i) } else { None }
    }).collect();
    if line.contains(&prefix) && positions.len() != line.matches(&prefix).count() { return err(format!("parameter {key} is not a token")); }
    if positions.len() != 1 { return err(format!("parameter {key} appears {} times", positions.len())); }
    let start = positions[0] + prefix.len();
    let end = line[start..].find(char::is_whitespace).map(|x| start + x).unwrap_or(line.len());
    if line[start..end].is_empty() { return err(format!("parameter {key} empty")); }
    let mut out = String::with_capacity(line.len() + value.len());
    out.push_str(&line[..start]); out.push_str(value); out.push_str(&line[end..]); Ok(out)
}

fn materialize_deck(source: &Path, out: &Path, point: &Point) -> Result<(String, String), String> {
    fs::create_dir_all(out).map_err(|e| e.to_string())?;
    let deck = read_text(&source.join("cold.cir"))?;
    let names = include_names(source)?;
    let includes_hash = include_digest(source, &names)?;
    let mut changed_vac = 0;
    let mut changed_load = 0;
    let mut rewritten = String::new();
    for raw in deck.split_inclusive('\n') {
        let has_v = raw.contains("VAC_RMS=");
        let has_r = raw.contains("RLOAD=");
        if (has_v || has_r) && !raw.trim_start().starts_with(".param") { return err("execution parameter appears outside .param line"); }
        let mut line = raw.to_string();
        if has_v { line = replace_param(&line, "VAC_RMS", &format!("{:.9}", point.line_v))?; changed_vac += 1; }
        if has_r { line = replace_param(&line, "RLOAD", &format!("{:.12}", point.rload))?; changed_load += 1; }
        rewritten.push_str(&line);
    }
    if changed_vac != 1 || changed_load != 1 { return err(format!("expected one VAC_RMS and one RLOAD token, found {changed_vac} and {changed_load}")); }
    // Ensure only the two declared scalar tokens differ from the source deck.
    let deck_hash = hash_bytes(rewritten.as_bytes())?;
    fs::write(out.join("cold.cir"), rewritten).map_err(|e| e.to_string())?;
    for n in &names {
        let target = out.join(n);
        if let Some(parent) = target.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
        fs::copy(source.join(n), &target).map_err(|e| format!("copy {n}: {e}"))?;
    }
    let meta = format!("{{\n  \"id\": \"{}\",\n  \"line_v_rms\": {:.9},\n  \"rload_ohm\": {:.12},\n  \"source_deck_sha256\": \"{}\",\n  \"generated_deck_sha256\": \"{}\",\n  \"source_includes_sha256\": \"{}\",\n  \"status\": \"materialized\"\n}}\n", point.id, point.line_v, point.rload, sha256_file(&source.join("cold.cir"))?, deck_hash, includes_hash);
    fs::write(out.join("case.json"), meta).map_err(|e| e.to_string())?;
    Ok((deck_hash, includes_hash))
}

fn shell_quote(path: &Path) -> String {
    let s = path.to_string_lossy(); format!("'{}'", s.replace('\'', "'\\''"))
}

fn compressor_shell_command(compressor: &Compressor, fifo: &Path, output: &Path) -> String {
    let flags = if compressor.pigz { "-p 4 -c" } else { "-c" };
    format!("exec {} {} < {} > {}", shell_quote(&compressor.path), flags, shell_quote(fifo), shell_quote(output))
}

#[cfg(unix)]
fn install_export_fd(cmd: &mut Command, write_fd: RawFd) {
    // `Stdio::piped` gives pigz a dedicated anonymous pipe. The native host
    // receives its actual owned descriptor as `/dev/fd/N`. Clear CLOEXEC in
    // the child before exec; retaining the dynamic descriptor avoids
    // clobbering Rust's internal child-error pipe when fd 3 is occupied.
    unsafe {
        cmd.pre_exec(move || {
            let flags = fcntl(write_fd, F_GETFD);
            if flags < 0 || fcntl(write_fd, F_SETFD, flags & !FD_CLOEXEC) < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

fn tracked_args(wall_limit: u64, end_s: f64, export_path: &str, first_invalid_snapshot: bool) -> Vec<String> {
    let mut args = vec!["cold.cir".to_string(), wall_limit.to_string(), end_s.to_string(), export_path.to_string()];
    let _ = first_invalid_snapshot;
    args.push("first-invalid.tsv".to_string());
    args
}

fn run_native_scan(case: &Path, decoder: &Path, normalize: &Path, consumer: &Path, consumer_args: &[String], rload: f64, output: &Path, stderr: &Path) -> Result<(ExitStatus, ExitStatus, ExitStatus, ExitStatus), String> {
    let raw = case.join("raw.trace.raw.gz");
    let mut gunzip = Command::new("gzip").args(["-cd", raw.to_str().ok_or("invalid raw gzip path")?]).stdout(Stdio::piped()).stderr(Stdio::null()).spawn().map_err(|e| e.to_string())?;
    let gunzip_stdout = gunzip.stdout.take().ok_or_else(|| { reap_child(&mut gunzip); "gzip stdout".to_string() })?;
    let mut adapter = match Command::new(decoder).args(["--schema", "normal15", "--byte-order", "little"]).stdin(gunzip_stdout).stdout(Stdio::piped()).stderr(Stdio::null()).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut gunzip); return err(format!("decoder spawn: {e}")); }
    };
    let adapter_stdout = adapter.stdout.take().ok_or_else(|| { reap_child(&mut adapter); reap_child(&mut gunzip); "decoder stdout".to_string() })?;
    let mut normalizer = match Command::new(normalize).arg(format!("{rload:.12}")).stdin(adapter_stdout).stdout(Stdio::piped()).stderr(Stdio::null()).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut adapter); reap_child(&mut gunzip); return err(format!("normalizer spawn: {e}")); }
    };
    let normalizer_stdout = normalizer.stdout.take().ok_or_else(|| { reap_child(&mut normalizer); reap_child(&mut adapter); reap_child(&mut gunzip); "normalizer stdout".to_string() })?;
    let report = File::create(output).map_err(|e| { reap_child(&mut normalizer); reap_child(&mut adapter); reap_child(&mut gunzip); format!("consumer report: {e}") })?;
    let stderr_file = File::create(stderr).map_err(|e| { reap_child(&mut normalizer); reap_child(&mut adapter); reap_child(&mut gunzip); format!("consumer stderr: {e}") })?;
    let mut consumer = match Command::new(consumer).args(consumer_args).stdin(normalizer_stdout).stdout(Stdio::from(report)).stderr(Stdio::from(stderr_file)).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut normalizer); reap_child(&mut adapter); reap_child(&mut gunzip); return err(format!("consumer spawn: {e}")); }
    };
    let mut children = [&mut consumer, &mut normalizer, &mut adapter, &mut gunzip];
    let statuses = wait_pipeline_children(&mut children, Duration::from_secs(900), case)?;
    Ok((statuses[0], statuses[1], statuses[2], statuses[3]))
}

fn run_native_audit(case: &Path, decoder: &Path, event_audit: &Path, rload: f64, end_s: f64) -> Result<ExitStatus, String> {
    let raw = case.join("raw.trace.raw.gz");
    let mut gunzip = Command::new("gzip").args(["-cd", raw.to_str().ok_or("invalid raw gzip path")?]).stdout(Stdio::piped()).stderr(Stdio::null()).spawn().map_err(|e| e.to_string())?;
    let gunzip_stdout = gunzip.stdout.take().ok_or_else(|| { reap_child(&mut gunzip); "gzip stdout".to_string() })?;
    let mut decoder_child = match Command::new(decoder).args(["--schema", "normal15", "--byte-order", "little"]).stdin(gunzip_stdout).stdout(Stdio::piped()).stderr(Stdio::null()).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut gunzip); return err(format!("decoder spawn: {e}")); }
    };
    let decoder_stdout = decoder_child.stdout.take().ok_or_else(|| { reap_child(&mut decoder_child); reap_child(&mut gunzip); "decoder stdout".to_string() })?;
    let audit_output = File::create(case.join("raw15-event-audit.txt")).map_err(|e| { reap_child(&mut decoder_child); reap_child(&mut gunzip); e.to_string() })?;
    let audit_error = File::create(case.join("raw15-event-audit.stderr")).map_err(|e| { reap_child(&mut decoder_child); reap_child(&mut gunzip); e.to_string() })?;
    let events_path = case.join("owned-events.tsv");
    let end_arg = format!("{end_s:.12}");
    let rload_arg = format!("{rload:.12}");
    let events_arg = events_path.to_str().ok_or("invalid events path")?;
    let mut audit_child = match Command::new(event_audit).args(["--end-s", &end_arg, "--rload", &rload_arg, "--events", events_arg]).stdin(decoder_stdout).stdout(Stdio::from(audit_output)).stderr(Stdio::from(audit_error)).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut decoder_child); reap_child(&mut gunzip); return err(format!("event audit spawn: {e}")); }
    };
    let mut children = [&mut audit_child, &mut decoder_child, &mut gunzip];
    let statuses = wait_pipeline_children(&mut children, Duration::from_secs(900), case)?;
    let audit = statuses[0];
    let decoder_status = statuses[1];
    let gzip_status = statuses[2];
    if !audit.success() || !decoder_status.success() || !gzip_status.success() { return err(format!("event audit pipeline failed audit={audit} decoder={decoder_status} gzip={gzip_status}")); }
    Ok(audit)
}

fn wait_pipeline_children(children: &mut [&mut Child], limit: Duration, disk_probe: &Path) -> Result<Vec<ExitStatus>, String> {
    let started = Instant::now();
    let mut statuses: Vec<Option<ExitStatus>> = vec![None; children.len()];
    loop {
        for (index, child) in children.iter_mut().enumerate() {
            if statuses[index].is_none() {
                match child.try_wait() {
                    Ok(status) => statuses[index] = status,
                    Err(error) => {
                        for sibling in children.iter_mut() { reap_child(sibling); }
                        return err(format!("pipeline wait failed: {error}"));
                    }
                }
            }
        }
        if statuses.iter().all(Option::is_some) {
            return Ok(statuses.into_iter().map(Option::unwrap).collect());
        }
        if available_bytes(disk_probe).unwrap_or(0) < 10 * 1024 * 1024 * 1024 {
            for child in children.iter_mut() { reap_child(child); }
            return err("free space fell below 10 GiB during native analysis");
        }
        if started.elapsed() >= limit {
            for child in children.iter_mut() { reap_child(child); }
            return err(format!("native pipeline exceeded {}s", limit.as_secs()));
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn run_native_pipeline(case: &Path, decoder: &Path, normalize: &Path, checker: &Path, event_metrics: &Path, event_audit: &Path, rload: f64, end_s: f64) -> Result<bool, String> {
    let audit = run_native_audit(case, decoder, event_audit, rload, end_s)?;
    let expected_rows: u64 = jq(&case.join("capture-metadata.json"), ".points")?.trim().parse().map_err(|_| "native metadata points is invalid")?;
    let audit_header = read_text(&case.join("raw15-event-audit.txt"))?.lines().next().ok_or("event audit report is empty")?.to_string();
    let reported_rows: u64 = audit_header.split_whitespace().find_map(|field| field.strip_prefix("rows=")).ok_or("event audit report has no rows field")?.parse().map_err(|_| "event audit rows is invalid")?;
    if reported_rows != expected_rows { return err(format!("event audit rows {reported_rows} != native metadata points {expected_rows}")); }
    let checker_args = vec!["--end-s".to_string(), format!("{end_s:.12}")];
    let checker = run_native_scan(case, decoder, normalize, checker, &checker_args, rload, &case.join("checker-report.txt"), &case.join("checker.stderr"))?;
    let metrics_args = vec!["--end-s".to_string(), format!("{end_s:.12}")];
    let metrics = run_native_scan(case, decoder, normalize, event_metrics, &metrics_args, rload, &case.join("event-metrics.txt"), &case.join("event-metrics.stderr"))?;
    let report = format!("{{\n  \"event_audit_exit\": {},\n  \"checker_exit\": {},\n  \"checker_normalizer_exit\": {},\n  \"checker_decoder_exit\": {},\n  \"checker_gzip_exit\": {},\n  \"metrics_exit\": {},\n  \"metrics_normalizer_exit\": {},\n  \"metrics_decoder_exit\": {},\n  \"metrics_gzip_exit\": {}\n}}\n", audit.code().unwrap_or(-1), checker.0.code().unwrap_or(-1), checker.1.code().unwrap_or(-1), checker.2.code().unwrap_or(-1), checker.3.code().unwrap_or(-1), metrics.0.code().unwrap_or(-1), metrics.1.code().unwrap_or(-1), metrics.2.code().unwrap_or(-1), metrics.3.code().unwrap_or(-1));
    fs::write(case.join("native-pipeline.json"), report).map_err(|e| e.to_string())?;
    let checker_stderr = read_text(&case.join("checker.stderr")).unwrap_or_default();
    let strict_rejection = checker.0.code() == Some(1)
        && checker_stderr.contains("time not strictly increasing");
    if !audit.success() || !metrics.0.success() || !metrics.1.success() || !metrics.2.success() || !metrics.3.success() || (!strict_rejection && (!checker.0.success() || !checker.1.success() || !checker.2.success() || !checker.3.success())) {
        return err("native decode/normalizer/event-metrics/checker pipeline failed; inspect per-tool reports");
    }
    Ok(checker.0.success())
}

fn validate_native_metadata(case: &Path) -> Result<(), String> {
    let metadata = case.join("capture-metadata.json");
    let ok = jq(&metadata, r#"if (type=="object" and .diagnostic_only==true and .accepted==false and .export_format=="ngspice-real-native" and .byte_order=="little" and .schema=="normal15" and .validation_policy=="event-aware-normal-v1" and .seen_names_mask==65535 and .expected_names_mask==65535 and (.points|type)=="number" and .points>=2 and .backwards_count==0 and .stop_reason=="solver_stopped") then "ok" else error("native capture metadata contract failed") end"#)?;
    if ok.trim() != "ok" { return err("native capture metadata contract failed"); }
    let stop = read_text(&case.join("stop.txt"))?;
    if !stop.lines().any(|line| line.trim() == "reason=solver_stopped") { return err("native stop receipt is not solver_stopped"); }
    Ok(())
}

fn case_sources_stable(case: &Path, source: &Path, names: &[String]) -> Result<bool, String> {
    let generated = jq(&case.join("case.json"), ".generated_deck_sha256")?.trim().to_string();
    if generated != sha256_file(&case.join("cold.cir"))? { return Ok(false); }
    for name in names {
        if sha256_file(&source.join(name))? != sha256_file(&case.join(name))? { return Ok(false); }
    }
    Ok(true)
}

fn reap_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

fn wait_bounded(child: &mut Child, limit: Duration) -> Result<ExitStatus, String> {
    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? { return Ok(status); }
        if started.elapsed() >= limit {
            let _ = child.kill(); let _ = child.wait();
            return err(format!("child did not exit within {}s", limit.as_secs()));
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn wait_bounded_disk(child: &mut Child, limit: Duration, disk_probe: &Path) -> Result<ExitStatus, String> {
    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? { return Ok(status); }
        if available_bytes(disk_probe).unwrap_or(0) < 10 * 1024 * 1024 * 1024 {
            reap_child(child);
            return err("free space fell below 10 GiB during raw compression");
        }
        if started.elapsed() >= limit {
            reap_child(child);
            return err(format!("compressor did not exit within {}s", limit.as_secs()));
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn available_bytes(path: &Path) -> Result<u64, String> {
    let out = Command::new("df").args(["-Pk", path.to_str().ok_or("invalid disk path")?]).output().map_err(|e| format!("df: {e}"))?;
    if !out.status.success() { return err("df failed"); }
    let text = String::from_utf8_lossy(&out.stdout);
    let line = text.lines().last().ok_or("df returned no filesystem row")?.split_whitespace().nth(3).ok_or("df returned no available column")?;
    let kib: u64 = line.parse().map_err(|_| "df available value invalid")?;
    kib.checked_mul(1024).ok_or_else(|| "df available value overflow".into())
}

fn run_pipeline(case: &Path, normalize: &Path, checker: &Path, rload: f64, end_s: f64) -> Result<ExitStatus, String> {
    let gz = case.join("trace.tsv.gz");
    let mut gunzip = Command::new("gzip").args(["-cd", gz.to_str().ok_or("invalid gzip path")?]).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?;
    let gunzip_stdout = gunzip.stdout.take().ok_or_else(|| { reap_child(&mut gunzip); "gzip stdout".to_string() })?;
    let mut adapter = Command::new(normalize).arg(format!("{rload:.12}")).stdin(gunzip_stdout).stdout(Stdio::piped()).spawn().map_err(|e| { reap_child(&mut gunzip); e.to_string() })?;
    let report = File::create(case.join("checker-report.txt")).map_err(|e| { reap_child(&mut adapter); reap_child(&mut gunzip); e.to_string() })?;
    let adapter_stdout = adapter.stdout.take().ok_or_else(|| { reap_child(&mut adapter); reap_child(&mut gunzip); "adapter stdout".to_string() })?;
    let mut check = Command::new(checker).args(["--end-s", &format!("{end_s:.12}")]).stdin(adapter_stdout).stdout(Stdio::from(report)).spawn().map_err(|e| { reap_child(&mut adapter); reap_child(&mut gunzip); e.to_string() })?;
    let check_status = check.wait().map_err(|e| e.to_string())?;
    let adapter_status = adapter.wait().map_err(|e| e.to_string())?;
    let gzip_status = gunzip.wait().map_err(|e| e.to_string())?;
    if !gzip_status.success() || !adapter_status.success() { return err(format!("pipeline failed gzip={gzip_status} normalize={adapter_status}")); }
    Ok(check_status)
}

fn main_run(mut c: Config) -> Result<(), String> {
    // Resolve all executable/input paths before any child changes its cwd.
    // Relative tool paths otherwise resolve inside LL01 and can silently run
    // a different binary (or fail only after a worker has started).
    c.source_dir = fs::canonicalize(&c.source_dir).map_err(|e| format!("source: {e}"))?;
    c.baseline = fs::canonicalize(&c.baseline).map_err(|e| format!("baseline: {e}"))?;
    c.manifest = fs::canonicalize(&c.manifest).map_err(|e| format!("manifest: {e}"))?;
    c.tracked = fs::canonicalize(&c.tracked).map_err(|e| format!("tracked: {e}"))?;
    c.normalize = fs::canonicalize(&c.normalize).map_err(|e| format!("normalize: {e}"))?;
    c.checker = fs::canonicalize(&c.checker).map_err(|e| format!("checker: {e}"))?;
    c.decoder = fs::canonicalize(&c.decoder).map_err(|e| format!("decoder: {e}"))?;
    c.event_metrics = fs::canonicalize(&c.event_metrics).map_err(|e| format!("event metrics: {e}"))?;
    c.event_audit = fs::canonicalize(&c.event_audit).map_err(|e| format!("event audit: {e}"))?;
    if let Some(s) = c.spice_scripts.take() { c.spice_scripts = Some(fs::canonicalize(s).map_err(|e| format!("spice scripts: {e}"))?); }
    let compressor = compressor_for(c.pigz.as_deref())?;
    let disk_probe = c.output.parent().unwrap_or(Path::new("."));
    if available_bytes(disk_probe)? < 10 * 1024 * 1024 * 1024 { return err("less than 10 GiB free before native run"); }
    let baseline = read_text(&c.baseline)?;
    // jq performs strict JSON parsing and all semantic validation. The raw
    // key-count guard rejects duplicate critical keys, which JSON parsers
    // commonly collapse with last-key-wins semantics.
    for key in ["accepted_for_operating_matrix_baseline", "policy_version", "source_sha256"] {
        if json_key_count(&baseline, key) > 1 { return err(format!("baseline contains duplicate {key} key")); }
    }
    let valid = jq(&c.baseline, r#". as $r | if ($r.accepted_for_operating_matrix_baseline==true and $r.policy_version=="event-aware-normal-v1" and ($r.source_sha256|type=="object") and (["cold.cir","protection.inc","standby.inc","clamp.inc","ucc28180-pwm-latch.inc","authored_logic_hysteretic.inc"] | all(. as $k | ($r.source_sha256[$k]|type=="string" and test("^[0-9a-f]{64}$"))))) then "ok" else error("baseline is not the event-aware accepted hash-bound receipt") end"#)?;
    if valid.trim() != "ok" { return err("baseline receipt is not explicitly accepted; refusing to execute grid"); }
    let baseline_end = jq(&c.baseline, r#"(.trace.end_s)"#)?.trim().parse::<f64>().map_err(|_| "baseline trace endpoint is invalid")?;
    if !baseline_end.is_finite() || baseline_end <= 0.0 || (baseline_end - c.end_s).abs() > 1e-12 {
        return err(format!("requested --end-s {} does not match accepted baseline endpoint {}", c.end_s, baseline_end));
    }
    let deck = c.source_dir.join("cold.cir");
    let deck_hash = sha256_file(&deck)?;
    let names = include_names(&c.source_dir)?;
    let inc_hash = include_digest(&c.source_dir, &names)?;
    let baseline_hash = |name: &str| jq(&c.baseline, &format!(".source_sha256[\"{name}\"]"));
    for name in ["cold.cir", "protection.inc", "standby.inc", "clamp.inc", "ucc28180-pwm-latch.inc", "authored_logic_hysteretic.inc"] {
        let expected = if name == "cold.cir" { deck_hash.clone() } else { sha256_file(&c.source_dir.join(name))? };
        if baseline_hash(name)?.trim() != expected { return err(format!("baseline source hash does not match {name}")); }
    }
    // Parse and validate all nine manifest rows before applying an optional
    // selection. A staged run must never use selection as a way to bypass
    // malformed or duplicate rows in the original manifest.
    let all_points = parse_points(&c.manifest)?;
    let points = select_points(all_points, c.selected_cases.as_deref())?;
    let selected_ids: Vec<String> = points.iter().map(|point| point.id.clone()).collect();
    if c.output.exists() { return err(format!("output already exists: {} (refusing overwrite)", c.output.display())); }
    fs::create_dir_all(&c.output).map_err(|e| e.to_string())?;
    let tool_hashes = [sha256_file(&c.tracked)?, sha256_file(&c.normalize)?, sha256_file(&c.checker)?, sha256_file(&c.decoder)?, sha256_file(&c.event_metrics)?, sha256_file(&c.event_audit)?, sha256_file(&c.manifest)?, sha256_file(&c.baseline)?];
    fs::write(c.output.join("source-identity.json"), format!("{{\n  \"deck_sha256\": \"{deck_hash}\",\n  \"includes_sha256\": \"{inc_hash}\",\n  \"tracked_sha256\": \"{}\",\n  \"normalize_sha256\": \"{}\",\n  \"checker_sha256\": \"{}\",\n  \"decoder_sha256\": \"{}\",\n  \"event_metrics_sha256\": \"{}\",\n  \"event_audit_sha256\": \"{}\",\n  \"baseline\": \"{}\",\n  \"selected_cases\": {},\n  \"selection_mode\": \"{}\",\n  \"tracked_cli_protocol\": [\"cold.cir\",\"<wall-seconds>\",\"<end-seconds>\",\"/dev/fd/<owned-pipe>\",\"first-invalid.tsv\"],\n  \"native_transport\": \"anonymous-pipe-dynamic-fd\",\n  \"first_invalid_snapshot\": {},\n  \"compressor\": {{\"path\": \"{}\", \"sha256\": \"{}\", \"threads\": {}, \"format\": \"{}\"}},\n  \"policy\": \"complete_review_pending\"\n}}\n", sha256_file(&c.tracked)?, sha256_file(&c.normalize)?, sha256_file(&c.checker)?, sha256_file(&c.decoder)?, sha256_file(&c.event_metrics)?, sha256_file(&c.event_audit)?, c.baseline.display(), json_string_array(&selected_ids), if c.selected_cases.is_some() { "explicit" } else { "default_all" }, c.first_invalid_snapshot, compressor.path.display(), sha256_file(&compressor.path)?, compressor.threads, if compressor.pigz { "gzip-compatible-pigz" } else { "gzip" })).map_err(|e| e.to_string())?;
    let mut queue: VecDeque<_> = points.into_iter().collect();
    let mut active: Vec<Running> = Vec::new();
    let mut failures = 0;
    let mut progress = File::create(c.output.join("runner-progress.tsv")).map_err(|e| e.to_string())?;
    writeln!(progress, "runner_wall_s\tcase\ttracked_wall_s\tsim_s\tpercent\tsim_per_wall\tcallbacks").map_err(|e| e.to_string())?;
    while !queue.is_empty() || !active.is_empty() {
        if available_bytes(disk_probe)? < 10 * 1024 * 1024 * 1024 {
            for running in &mut active { let _ = running.child.kill(); let _ = running.compressor.kill(); }
            return err("free space fell below 10 GiB during native run");
        }
        while active.len() < c.workers {
            let Some(point) = queue.pop_front() else { break; };
            let dir = c.output.join(&point.id);
            let _ = materialize_deck(&c.source_dir, &dir, &point)?;
            // Start compression with an anonymous stdin pipe. The parent
            // never opens a named FIFO and therefore cannot leave a writer
            // competing with the host's export stream.
            let mut gzip_cmd = Command::new(&compressor.path);
            if compressor.pigz { gzip_cmd.args(["-p", "4", "-c"]); } else { gzip_cmd.arg("-c"); }
            let gzip_log = File::create(dir.join("gzip.log")).map_err(|e| e.to_string())?;
            let mut gzip = gzip_cmd.stdin(Stdio::piped()).stdout(File::create(dir.join("raw.trace.raw.gz")).map_err(|e| e.to_string())?).stderr(Stdio::from(gzip_log)).spawn().map_err(|e| e.to_string())?;
            let write_end = gzip.stdin.take().ok_or_else(|| "compressor stdin pipe missing".to_string())?;
            let write_fd = write_end.as_raw_fd();
            let export_path = format!("/dev/fd/{write_fd}");
            let log = match File::create(dir.join("run.log")) {
                Ok(f) => f,
                Err(e) => { drop(write_end); let _ = gzip.kill(); let _ = gzip.wait(); return err(format!("run.log: {e}")); }
            };
            let tracked_arg_strings = tracked_args(c.wall_limit, c.end_s, &export_path, c.first_invalid_snapshot);
            let tracked_args_ref: Vec<&str> = tracked_arg_strings.iter().map(String::as_str).collect();
            let mut cmd = Command::new(&c.tracked);
            let log_copy = match log.try_clone() {
                Ok(f) => f,
                Err(e) => { drop(write_end); let _ = gzip.kill(); let _ = gzip.wait(); return err(format!("run.log clone: {e}")); }
            };
            cmd.current_dir(&dir).args(&tracked_args_ref).stdout(log_copy).stderr(Stdio::from(log));
            if let Some(s) = &c.spice_scripts { cmd.env("SPICE_SCRIPTS", s); }
            #[cfg(unix)]
            install_export_fd(&mut cmd, write_fd);
            let child = match cmd.spawn() {
                Ok(c) => { drop(write_end); c },
                Err(e) => { drop(write_end); let _ = gzip.kill(); let _ = gzip.wait(); return err(format!("spawn {}: {e}", point.id)); }
            };
            let transport_identity = format!("{{\n  \"transport\": \"anonymous-pipe\",\n  \"native_export_path\": \"{}\",\n  \"native_cli_args\": [\"cold.cir\",\"{}\",\"{}\",\"{}\",\"first-invalid.tsv\"],\n  \"compressor_stdin_fd\": {}\n}}\n", json_escape(&export_path), c.wall_limit, c.end_s, json_escape(&export_path), write_fd);
            if let Err(error) = fs::write(dir.join("transport-identity.json"), transport_identity) {
                let mut child = child;
                let _ = child.kill(); let _ = child.wait();
                let _ = gzip.kill(); let _ = gzip.wait();
                return err(format!("transport identity: {error}"));
            }
            eprintln!("started {} (workers {}/{})", point.id, active.len() + 1, c.workers);
            active.push(Running { point, dir, child, compressor: gzip, started: Instant::now(), last_progress: String::new() });
        }
        let mut i = 0;
        while i < active.len() {
            let r = &mut active[i];
            if let Ok(Some(compressor_status)) = r.compressor.try_wait() {
                if !compressor_status.success() && r.child.try_wait().ok().flatten().is_none() {
                    let _ = r.child.kill(); let _ = r.child.wait();
                    failures += 1;
                    fs::write(r.dir.join("result.json"), format!("{{\n  \"id\": \"{}\",\n  \"status\": \"runner_failure\",\n  \"reason\": \"compressor exited before producer\",\n  \"compressor_exit\": {}\n}}\n", r.point.id, compressor_status.code().unwrap_or(-1))).map_err(|e| e.to_string())?;
                    active.swap_remove(i);
                    continue;
                }
            }
            if let Ok(Some(status)) = r.child.try_wait() {
                // The tracked producer has closed the FIFO by the time it
                // exits. Wait for compression to finish before opening the
                // gzip, otherwise the checker can observe a truncated file.
                // ngSpice_Command can return success after a parse failure.
                // With no plot, no FIFO writer opens; do not wait 900s for
                // the reader when the producer already reports zero points.
                let gzip_result = if status.success() && validate_native_metadata(&r.dir).is_ok() {
                    wait_bounded_disk(&mut r.compressor, Duration::from_secs(900), disk_probe)
                } else {
                    let _ = r.compressor.kill(); let _ = r.compressor.wait();
                    Err("tracked host failed before complete FIFO export".to_string())
                };
                let pipeline = if status.success() && gzip_result.as_ref().map(|s| s.success()).unwrap_or(false) && r.dir.join("raw.trace.raw.gz").is_file() {
                    validate_native_metadata(&r.dir).and_then(|_| run_native_pipeline(&r.dir, &c.decoder, &c.normalize, &c.checker, &c.event_metrics, &c.event_audit, r.point.rload, c.end_s))
                } else { Err(format!("tracked/compressor incomplete: tracked={status}, compressor={gzip_result:?}")) };
                let source_stable = sha256_file(&c.source_dir.join("cold.cir")).ok().is_some_and(|hash| hash == deck_hash)
                    && include_digest(&c.source_dir, &names).ok().is_some_and(|hash| hash == inc_hash)
                    && case_sources_stable(&r.dir, &c.source_dir, &names).unwrap_or(false)
                    && [sha256_file(&c.tracked), sha256_file(&c.normalize), sha256_file(&c.checker), sha256_file(&c.decoder), sha256_file(&c.event_metrics), sha256_file(&c.event_audit), sha256_file(&c.manifest), sha256_file(&c.baseline)].iter().enumerate().all(|(index, hash)| hash.as_ref().is_ok_and(|value| value == &tool_hashes[index]));
                let pipeline = if !source_stable { Err("source closure changed during native run".to_string()) } else { pipeline };
                let result = match pipeline {
                    Ok(checker_accepted) => { eprintln!("{} complete; checker_exit={} review pending (no automatic acceptance)", r.point.id, if checker_accepted { 0 } else { 1 }); "complete_review_pending" },
                    Err(e) => { eprintln!("{} runner failure: {e}", r.point.id); failures += 1; "runner_failure" },
                };
                fs::write(r.dir.join("result.json"), format!("{{\n  \"id\": \"{}\",\n  \"status\": \"{result}\",\n  \"tracked_exit\": {},\n  \"elapsed_s\": {:.3},\n  \"policy\": \"complete_review_pending\"\n}}\n", r.point.id, status.code().unwrap_or(-1), r.started.elapsed().as_secs_f64())).map_err(|e| e.to_string())?;
                active.swap_remove(i);
                continue;
            }
            if r.started.elapsed() > Duration::from_secs(c.wall_limit.saturating_add(600)) {
                let _ = r.child.kill(); let _ = r.child.wait(); let _ = r.compressor.kill(); let _ = r.compressor.wait(); failures += 1;
                fs::write(r.dir.join("result.json"), format!("{{\n  \"id\": \"{}\",\n  \"status\": \"scheduler_timeout\"\n}}\n", r.point.id)).map_err(|e| e.to_string())?;
                active.swap_remove(i); continue;
            }
            if let Ok(p) = read_text(&r.dir.join("progress.tsv")) {
                if let Some(last) = p.lines().last() {
                    if last != r.last_progress { writeln!(progress, "{:.3}\t{}\t{}", r.started.elapsed().as_secs_f64(), r.point.id, last).map_err(|e| e.to_string())?; progress.flush().map_err(|e| e.to_string())?; r.last_progress = last.to_string(); }
                }
            }
            i += 1;
        }
        if !active.is_empty() { thread::sleep(Duration::from_secs(5)); }
    }
    if failures != 0 { return err(format!("line/load run completed with {failures} failed points")); }
    fs::write(c.output.join("status.json"), format!("{{\"status\":\"complete_review_pending\",\"selected_cases\":{},\"policy\":\"event-aware-normal-v1\"}}\n", json_string_array(&selected_ids))).map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    match parse_args().and_then(|c| if c.self_test { self_test() } else if c.inspect { inspect_run(c) } else { main_run(c) }) {
        Ok(()) => {}, Err(e) => { eprintln!("ERROR: {e}"); std::process::exit(1); }
    }
}

fn inspect_run(mut c: Config) -> Result<(), String> {
    c.source_dir = fs::canonicalize(&c.source_dir).map_err(|e| format!("source: {e}"))?;
    c.baseline = fs::canonicalize(&c.baseline).map_err(|e| format!("baseline: {e}"))?;
    c.manifest = fs::canonicalize(&c.manifest).map_err(|e| format!("manifest: {e}"))?;
    for (name, path) in [("tracked", &c.tracked), ("normalize", &c.normalize), ("checker", &c.checker), ("decoder", &c.decoder), ("event-metrics", &c.event_metrics), ("event-audit", &c.event_audit)] {
        let resolved = fs::canonicalize(path).map_err(|e| format!("{name}: {e}"))?;
        if !resolved.is_file() { return err(format!("{name} is not a file")); }
    }
    let baseline = read_text(&c.baseline)?;
    if json_key_count(&baseline, "accepted_for_operating_matrix_baseline") > 1 { return err("duplicate baseline acceptance key"); }
    if jq(&c.baseline, r#"if (.accepted_for_operating_matrix_baseline==true and .policy_version=="event-aware-normal-v1") then "ok" else error("baseline policy/acceptance mismatch") end"#)?.trim() != "ok" { return err("baseline policy/acceptance mismatch"); }
    let points = parse_points(&c.manifest)?;
    let selected = select_points(points, c.selected_cases.as_deref())?;
    let names = include_names(&c.source_dir)?;
    let deck_hash = sha256_file(&c.source_dir.join("cold.cir"))?;
    let include_hash = include_digest(&c.source_dir, &names)?;
    if available_bytes(c.output.parent().unwrap_or(Path::new(".")))? < 10 * 1024 * 1024 * 1024 { return err("less than 10 GiB free"); }
    println!("preflight=READY policy=event-aware-normal-v1 cases={} deck_sha256={} includes_sha256={} end_s={:.17e} workers={}", selected.len(), deck_hash, include_hash, c.end_s, c.workers);
    Ok(())
}

fn self_test() -> Result<(), String> {
    // Cheap deterministic checks used before an expensive nine-point run.
    let tmp = env::temp_dir().join(format!("matrix07-line-load-selftest-{}", std::process::id()));
    if tmp.exists() { fs::remove_dir_all(&tmp).map_err(|e| e.to_string())?; }
    fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
    let all_cases: Vec<_> = (1..=9).map(|index| Point { id: format!("LL{index:02}"), line_v: 100.0 + index as f64, rload: 200.0 + index as f64 }).collect();
    if select_points(all_cases.clone(), None)?.len() != 9 { return err("self-test default case selection changed"); }
    let selected = vec!["LL02".to_string(), "LL01".to_string()];
    let staged = select_points(all_cases.clone(), Some(&selected))?;
    if staged.iter().map(|point| point.id.as_str()).collect::<Vec<_>>() != ["LL01", "LL02"] { return err("self-test selected cases lost manifest order"); }
    if select_points(all_cases.clone(), Some(&["LL01".to_string(), "LL01".to_string()])).is_ok() { return err("self-test duplicate case selection accepted"); }
    if select_points(all_cases, Some(&["LL99".to_string()])).is_ok() { return err("self-test unknown case selection accepted"); }
    let four = tracked_args(1800, 0.5, "/dev/fd/42", false);
    let five = tracked_args(1800, 0.5, "/dev/fd/42", true);
    if four.len() != 5 || four[3] != "/dev/fd/42" || four[4] != "first-invalid.tsv" || five != four { return err("self-test native five-argument CLI protocol mismatch"); }
    let gzip = compressor_for(None)?;
    let pigz = compressor_for(Some(Path::new("pigz")))?;
    let command_fifo = Path::new("case/trace.fifo");
    let command_output = Path::new("case/trace.tsv.gz");
    let gzip_command = compressor_shell_command(&gzip, command_fifo, command_output);
    let pigz_command = compressor_shell_command(&pigz, command_fifo, command_output);
    if !gzip_command.contains(" -c < '") || gzip_command.contains("-p 4") || !pigz_command.contains(" -p 4 -c < '") {
        return err("self-test compressor argument construction mismatch");
    }
    let source = tmp.join("source"); fs::create_dir_all(&source).map_err(|e| e.to_string())?;
    fs::write(source.join("cold.cir"), ".param VAC_RMS=120 RLOAD=190\n.include a.inc\n").map_err(|e| e.to_string())?;
    fs::write(source.join("a.inc"), "* immutable\n").map_err(|e| e.to_string())?;
    let p = Point { id: "T01".into(), line_v: 108.0, rload: 416.460488957 };
    let d = tmp.join("case"); let (h, _) = materialize_deck(&source, &d, &p)?;
    let text = read_text(&d.join("cold.cir"))?;
    if !text.contains("VAC_RMS=108.000000000 RLOAD=416.460488957000") || h == sha256_file(&source.join("cold.cir"))? { return err("self-test parameter materialization failed"); }
    let source_names = include_names(&source)?;
    let case_names = include_names(&d)?;
    if source_names != case_names || include_digest(&source, &source_names)? != include_digest(&d, &case_names)? { return err("self-test include mutation detected"); }
    // Exercise the real production deck shape: VAC_RMS and RLOAD live on
    // different .param lines, while RFREQ/FLINE/initial conditions must stay
    // byte-for-byte present in the generated source.
    let production = [PathBuf::from("../normal-tracked"), PathBuf::from("normal-tracked")]
        .into_iter().find(|p| p.join("cold.cir").is_file());
    let prod = production.ok_or("self-test requires normal-tracked/cold.cir from operating-matrix-07 or line-load-runner")?;
    let pd = tmp.join("production-case");
    let pp = Point { id: "LL01".into(), line_v: 108.0, rload: 416.460488957 };
    materialize_deck(&prod, &pd, &pp)?;
    let generated = read_text(&pd.join("cold.cir"))?;
    if !generated.contains("RFREQ=16.2k") || !generated.contains("FLINE=60") || !generated.contains("VAC_RMS=108.000000000") || !generated.contains("RLOAD=416.460488957000") {
        return err("self-test production deck materialization changed or lost unrelated parameters");
    }
    let original = read_text(&prod.join("cold.cir"))?;
    if restore_tokens(&generated, 120.0, 190.0)? != original { return err("self-test production deck changed bytes outside VAC_RMS/RLOAD"); }
    let vendor = [PathBuf::from("../normal-vendor-driver-candidate"), PathBuf::from("normal-vendor-driver-candidate")]
        .into_iter().find(|p| p.join("cold.cir").is_file());
    if let Some(vendor) = vendor {
        let vn = include_names(&vendor)?;
        if !vn.iter().any(|n| n == "vendor/UCC27511A.lib") { return err("self-test vendor include closure omitted UCC27511A.lib"); }
        let vd = tmp.join("vendor-case"); let vp = Point { id: "LL01".into(), line_v: 108.0, rload: 416.460488957 };
        materialize_deck(&vendor, &vd, &vp)?;
        if fs::read(vd.join("vendor/UCC27511A.lib")).map_err(|e| e.to_string())? != fs::read(vendor.join("vendor/UCC27511A.lib")).map_err(|e| e.to_string())? { return err("self-test vendor include bytes changed"); }
        let mutated = tmp.join("vendor-mutated"); fs::create_dir_all(mutated.join("vendor")).map_err(|e| e.to_string())?;
        fs::copy(vendor.join("cold.cir"), mutated.join("cold.cir")).map_err(|e| e.to_string())?;
        for n in &vn { let t = mutated.join(n); if let Some(p) = t.parent() { fs::create_dir_all(p).map_err(|e| e.to_string())?; } fs::copy(vendor.join(n), &t).map_err(|e| e.to_string())?; }
        let mut bytes = fs::read(mutated.join("vendor/UCC27511A.lib")).map_err(|e| e.to_string())?; bytes.push(b'\n'); fs::write(mutated.join("vendor/UCC27511A.lib"), bytes).map_err(|e| e.to_string())?;
        if include_digest(&vendor, &vn)? == include_digest(&mutated, &vn)? { return err("self-test vendor mutation did not change closure digest"); }
    }
    let escape = tmp.join("escape"); fs::create_dir_all(&escape).map_err(|e| e.to_string())?;
    fs::write(escape.join("cold.cir"), ".include ../outside.inc\n").map_err(|e| e.to_string())?;
    if include_names(&escape).is_ok() { return err("self-test traversal include was accepted"); }
    let missing = tmp.join("missing"); fs::create_dir_all(&missing).map_err(|e| e.to_string())?;
    fs::write(missing.join("cold.cir"), ".include absent.inc\n").map_err(|e| e.to_string())?;
    if include_names(&missing).is_ok() { return err("self-test missing include was accepted"); }
    fs::write(missing.join("cold.cir"), ".lib absent.lib\n").map_err(|e| e.to_string())?;
    if include_names(&missing).is_ok() { return err("self-test unsupported .lib directive was accepted"); }
    let encoded = tmp.join("encoded"); fs::create_dir_all(&encoded).map_err(|e| e.to_string())?;
    fs::write(encoded.join("cold.cir"), b".INCLUDE child.inc\n").map_err(|e| e.to_string())?;
    fs::write(encoded.join("child.inc"), b"* copyright \xff\n.include grand.inc\n").map_err(|e| e.to_string())?;
    fs::write(encoded.join("grand.inc"), b"* nested\n").map_err(|e| e.to_string())?;
    let en = include_names(&encoded)?;
    if !en.iter().any(|n| n == "grand.inc") { return err("self-test non-UTF8 nested include was dropped"); }
    #[cfg(unix)] {
        use std::os::unix::fs::symlink;
        let alias = tmp.join("symlink-alias"); fs::create_dir_all(&alias).map_err(|e| e.to_string())?;
        fs::write(alias.join("cold.cir"), ".include alias.inc\n").map_err(|e| e.to_string())?;
        fs::write(alias.join("real.inc"), b"* real\n").map_err(|e| e.to_string())?;
        symlink(alias.join("real.inc"), alias.join("alias.inc")).map_err(|e| e.to_string())?;
        if include_names(&alias).is_ok() { return err("self-test in-root symlink include was accepted"); }
    }
    // Exercise the exact decompression/adapter/checker process boundary with
    // synthetic commands.  A checker failure must remain a failure; the
    // orchestration layer never promotes a simulator or pipeline exit into a
    // circuit pass.
    let raw = d.join("trace.tsv");
    fs::write(&raw, "time v(acsrc)\n0 0\n").map_err(|e| e.to_string())?;
    let gz = File::create(d.join("trace.tsv.gz")).map_err(|e| e.to_string())?;
    let mut zip = Command::new("gzip").arg("-c").stdin(File::open(&raw).map_err(|e| e.to_string())?).stdout(Stdio::from(gz)).spawn().map_err(|e| e.to_string())?;
    if !zip.wait().map_err(|e| e.to_string())?.success() { return err("self-test gzip failed"); }
    let normalize = d.join("normalize");
    let checker_fail = d.join("checker-fail");
    let checker_pass = d.join("checker-pass");
    write_exec(&normalize, "#!/bin/sh\ncat\n")?;
    write_exec(&checker_fail, "#!/bin/sh\ncat >/dev/null\nexit 17\n")?;
    write_exec(&checker_pass, "#!/bin/sh\ncat >/dev/null\nexit 0\n")?;
    let failed = run_pipeline(&d, &normalize, &checker_fail, p.rload, DEFAULT_END_S)?;
    if failed.success() { return err("self-test accepted synthetic checker failure"); }
    let passed = run_pipeline(&d, &normalize, &checker_pass, p.rload, DEFAULT_END_S)?;
    if !passed.success() { return err("self-test rejected synthetic checker success"); }
    if run_pipeline(&d, &normalize, Path::new("/path/that/does/not/exist"), p.rload, DEFAULT_END_S).is_ok() { return err("self-test missing checker was accepted"); }
    let duplicate = d.join("duplicate-baseline.json");
    fs::write(&duplicate, b"{\"accepted\":true,\"accepted\":false}").map_err(|e| e.to_string())?;
    if json_key_count(&read_text(&duplicate)?, "accepted") != 2 { return err("self-test duplicate-key guard failed"); }
    let malformed = d.join("malformed.json");
    fs::write(&malformed, b"{not-json").map_err(|e| e.to_string())?;
    if jq(&malformed, ".") .is_ok() { return err("self-test malformed JSON was accepted"); }
    fifo_process_tests(&tmp, &pigz)?;
    anonymous_pipe_tests(&tmp, &pigz)?;
    native_fixture_pipe_test(&tmp, &pigz)?;
    println!("self-test: selection/materialization/hash/change-constraint/pipeline/process-fail-closed checks PASS");
    if env::var_os("MATRIX27_KEEP_SELFTEST").is_none() {
        fs::remove_dir_all(&tmp).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn anonymous_pipe_tests(tmp: &Path, compressor: &Compressor) -> Result<(), String> {
    for (name, payload) in [("small", b"native-pipe-small\n".to_vec()), ("large", vec![b'x'; 4 * 1024 * 1024])] {
        let dir = tmp.join(format!("anonymous-{name}"));
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let compressed = dir.join("trace.gz");
        let mut command = Command::new(&compressor.path);
        if compressor.pigz { command.args(["-p", "4", "-c"]); } else { command.arg("-c"); }
        let mut child = command.stdin(Stdio::piped()).stdout(File::create(&compressed).map_err(|e| e.to_string())?).spawn().map_err(|e| e.to_string())?;
        let mut input = child.stdin.take().ok_or("anonymous pipe stdin missing")?;
        input.write_all(&payload).map_err(|e| e.to_string())?;
        drop(input); // EOF must reach the compressor before wait.
        if !child.wait().map_err(|e| e.to_string())?.success() { return err(format!("anonymous {name} compressor failed")); }
        let decoded = Command::new("gzip").args(["-cd", compressed.to_str().ok_or("compressed path")?]).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?.wait_with_output().map_err(|e| e.to_string())?;
        if !decoded.status.success() || decoded.stdout != payload { return err(format!("anonymous {name} EOF roundtrip mismatch")); }
    }
    if Command::new("/path/that/does/not/exist").stdin(Stdio::piped()).spawn().is_ok() { return err("anonymous child startup failure unexpectedly succeeded"); }
    Ok(())
}

fn native_fixture_pipe_test(tmp: &Path, compressor: &Compressor) -> Result<(), String> {
    let real_source = env::var_os("MATRIX27_NATIVE_SOURCE").map(PathBuf::from);
    let fixture = env::var_os("MATRIX27_NATIVE_HOST").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/tmp/matrix07-synthetic-normal15-producer"));
    if !fixture.is_file() { return err(format!("self-test native fixture is missing: {}", fixture.display())); }
    let dir = tmp.join("native-fixture");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    if let Some(source) = &real_source {
        for name in ["cold.cir", "protection.inc", "standby.inc", "clamp.inc", "ucc28180-pwm-latch.inc", "authored_logic_hysteretic.inc"] {
            fs::copy(source.join(name), dir.join(name)).map_err(|e| format!("copy native source {name}: {e}"))?;
        }
        let cold = read_text(&dir.join("cold.cir"))?.replace("TSTOP=650m", "TSTOP=20u");
        fs::write(dir.join("cold.cir"), cold).map_err(|e| e.to_string())?;
    } else {
        fs::write(dir.join("cold.cir"), "* synthetic fixture deck\n").map_err(|e| e.to_string())?;
    }
    let target = if real_source.is_some() { "0.00002" } else { "0.65" };
    let wall = if real_source.is_some() { "20" } else { "20" };
    let raw = dir.join("raw.trace.raw.gz");
    let mut gzip_cmd = Command::new(&compressor.path);
    if compressor.pigz { gzip_cmd.args(["-p", "4", "-c"]); } else { gzip_cmd.arg("-c"); }
    let mut gzip = gzip_cmd.stdin(Stdio::piped()).stdout(File::create(&raw).map_err(|e| e.to_string())?).spawn().map_err(|e| e.to_string())?;
    let write_end = gzip.stdin.take().ok_or("fixture compressor stdin missing")?;
    let fd = write_end.as_raw_fd();
    let export_path = format!("/dev/fd/{fd}");
    let args = ["cold.cir", wall, target, export_path.as_str(), "first-invalid.tsv"];
    let mut host = Command::new(&fixture);
    host.current_dir(&dir).args(args);
    install_export_fd(&mut host, fd);
    let mut host = match host.spawn() {
        Ok(child) => child,
        Err(error) => { drop(write_end); reap_child(&mut gzip); return err(format!("fixture host spawn: {error}")); }
    };
    drop(write_end);
    let host_status = wait_bounded(&mut host, Duration::from_secs(20))?;
    let gzip_status = wait_bounded(&mut gzip, Duration::from_secs(20))?;
    if !host_status.success() || !gzip_status.success() { return err(format!("fixture host/compressor failed: {host_status} / {gzip_status}")); }
    validate_native_metadata(&dir)?;
    let gzip_check = Command::new("gzip").args(["-t", raw.to_str().ok_or("fixture raw path")?]).status().map_err(|e| e.to_string())?;
    if !gzip_check.success() { return err("fixture anonymous pipe gzip footer check failed"); }

    if let Some(source) = &real_source {
        // A direct regular-file run with the same 20 us deck is the payload
        // oracle. Ignore the textual native header and compare the complete
        // binary row payload after `Binary:\n` byte-for-byte.
        let reference = tmp.join("native-reference");
        fs::create_dir_all(&reference).map_err(|e| e.to_string())?;
        for name in ["cold.cir", "protection.inc", "standby.inc", "clamp.inc", "ucc28180-pwm-latch.inc", "authored_logic_hysteretic.inc"] {
            fs::copy(source.join(name), reference.join(name)).map_err(|e| format!("copy reference source {name}: {e}"))?;
        }
        let cold = read_text(&reference.join("cold.cir"))?.replace("TSTOP=650m", "TSTOP=20u");
        fs::write(reference.join("cold.cir"), cold).map_err(|e| e.to_string())?;
        let reference_path = reference.join("reference.native");
        let reference_args = ["cold.cir", wall, target, reference_path.to_str().ok_or("reference path")?, "first-invalid.tsv"];
        let reference_status = Command::new(&fixture).current_dir(&reference).args(reference_args).status().map_err(|e| e.to_string())?;
        if !reference_status.success() { return err(format!("reference native host failed: {reference_status}")); }
        let decompressed = dir.join("pipe.native");
        let decode_status = Command::new("gzip").args(["-cd", raw.to_str().ok_or("pipe raw path")?]).stdout(File::create(&decompressed).map_err(|e| e.to_string())?).status().map_err(|e| e.to_string())?;
        if !decode_status.success() { return err("pipe raw decompression failed"); }
        let native_parts = |path: &Path| -> Result<(Vec<u8>, Vec<u8>), String> {
            let bytes = fs::read(path).map_err(|e| e.to_string())?;
            let marker = b"Binary:\n";
            let offset = bytes.windows(marker.len()).position(|window| window == marker).ok_or_else(|| format!("native header missing in {}", path.display()))? + marker.len();
            Ok((bytes[..offset].to_vec(), bytes[offset..].to_vec()))
        };
        let (pipe_header, pipe_payload) = native_parts(&decompressed)?;
        let (reference_header, reference_payload) = native_parts(&reference_path)?;
        if pipe_payload != reference_payload { return err("anonymous pipe native payload differs from regular-file reference"); }
        let receipt_path = env::var_os("MATRIX27_PROBE_RECEIPT").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("line-load-native-runner-27/fixtures/real-native-20us-summary.json"));
        if pipe_payload.len() % (15 * std::mem::size_of::<f64>()) != 0 { return err("native payload is not an integral normal15 row count"); }
        let row_bytes = 15 * std::mem::size_of::<f64>();
        let first_time = f64::from_le_bytes(pipe_payload[0..8].try_into().map_err(|_| "first native time missing")?);
        let last_offset = pipe_payload.len() - row_bytes;
        let last_time = f64::from_le_bytes(pipe_payload[last_offset..last_offset + 8].try_into().map_err(|_| "last native time missing")?);
        let pipe_hash = sha256_file(&decompressed)?;
        let compressed_hash = sha256_file(&raw)?;
        let reference_hash = sha256_file(&reference_path)?;
        fs::write(receipt_path, format!("{{\n  \"status\":\"PROBE_ONLY\",\n  \"temporary_artifacts_dir\":\"{}\",\n  \"target_s\":0.00002,\n  \"pipe_host_exit\":{},\n  \"pipe_compressor_exit\":{},\n  \"reference_host_exit\":{},\n  \"pipe_compressed_sha256\":\"{}\",\n  \"pipe_header_sha256\":\"{}\",\n  \"reference_header_sha256\":\"{}\",\n  \"pipe_payload_bytes\":{},\n  \"reference_payload_bytes\":{},\n  \"decoded_rows\":{},\n  \"first_time_s\":{:.17e},\n  \"last_time_s\":{:.17e},\n  \"pipe_native_sha256\":\"{}\",\n  \"reference_native_sha256\":\"{}\",\n  \"payload_equal\":true,\n  \"acceptance\":false\n}}\n", json_escape(&tmp.display().to_string()), host_status.code().unwrap_or(-1), gzip_status.code().unwrap_or(-1), reference_status.code().unwrap_or(-1), compressed_hash, hash_bytes(&pipe_header)?, hash_bytes(&reference_header)?, pipe_payload.len(), reference_payload.len(), pipe_payload.len() / row_bytes, first_time, last_time, pipe_hash, reference_hash)).map_err(|e| e.to_string())?;
    }

    // A failed native-host spawn must close the only writer and let the
    // compressor observe EOF; this is the regression that the named FIFO
    // launch could leave blocked indefinitely.
    let failed_raw = dir.join("failed.raw.gz");
    let mut failed_cmd = Command::new(&compressor.path);
    if compressor.pigz { failed_cmd.args(["-p", "4", "-c"]); } else { failed_cmd.arg("-c"); }
    let mut failed_gzip = failed_cmd.stdin(Stdio::piped()).stdout(File::create(&failed_raw).map_err(|e| e.to_string())?).spawn().map_err(|e| e.to_string())?;
    let failed_end = failed_gzip.stdin.take().ok_or("failed compressor stdin missing")?;
    let failed_fd = failed_end.as_raw_fd();
    let mut missing = Command::new("/path/that/does/not/exist");
    install_export_fd(&mut missing, failed_fd);
    if missing.spawn().is_ok() { drop(failed_end); reap_child(&mut failed_gzip); return err("missing fixture host unexpectedly spawned"); }
    drop(failed_end);
    if !wait_bounded(&mut failed_gzip, Duration::from_secs(2))?.success() { return err("compressor did not observe EOF after host startup failure"); }
    Ok(())
}

fn restore_tokens(deck: &str, vac: f64, rload: f64) -> Result<String, String> {
    let mut restored = String::new();
    for raw in deck.split_inclusive('\n') {
        let mut line = raw.to_string();
        if line.contains("VAC_RMS=") { line = replace_param(&line, "VAC_RMS", &format!("{vac:.0}"))?; }
        if line.contains("RLOAD=") { line = replace_param(&line, "RLOAD", &format!("{rload:.0}"))?; }
        restored.push_str(&line);
    }
    Ok(restored)
}

fn fifo_process_tests(tmp: &Path, pigz: &Compressor) -> Result<(), String> {
    // Delayed EOF/footer: the reader must be reaped only after the producer
    // closes the FIFO, otherwise a valid trace can be mistaken for truncation.
    let delayed = tmp.join("delayed"); fs::create_dir_all(&delayed).map_err(|e| e.to_string())?;
    let fifo = delayed.join("trace.fifo");
    if !Command::new("mkfifo").arg(&fifo).status().map_err(|e| e.to_string())?.success() { return err("self-test mkfifo failed"); }
    if !is_fifo(&fifo)? { return err("self-test mkfifo did not create FIFO"); }
    let gzout = delayed.join("trace.gz");
    let mut reader = Command::new("sh").arg("-c").arg(format!("exec gzip -c < '{}' > '{}'", fifo.display(), gzout.display())).spawn().map_err(|e| e.to_string())?;
    let mut producer = Command::new("sh").arg("-c").arg(format!("sleep 0.2; printf payload > '{}'", fifo.display())).spawn().map_err(|e| e.to_string())?;
    if !producer.wait().map_err(|e| e.to_string())?.success() { return err("self-test delayed producer failed"); }
    if !wait_bounded(&mut reader, Duration::from_secs(2))?.success() || !gzout.is_file() { return err("self-test delayed FIFO footer was not drained"); }
    let gunzip = Command::new("gzip").args(["-cd", gzout.to_str().ok_or("gzip path")?]).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?;
    let out = gunzip.wait_with_output().map_err(|e| e.to_string())?;
    if !out.status.success() || out.stdout != b"payload" { return err("self-test delayed FIFO payload mismatch"); }
    let _ = fs::remove_file(&fifo);
    // A bounded real pigz sample must remain readable by the existing gzip
    // decompressor path. This exercises the same FIFO ownership and wait/reap
    // sequence used by the matrix scheduler, without running a simulation.
    let pigz_case = delayed.join("pigz-roundtrip");
    fs::create_dir_all(&pigz_case).map_err(|e| e.to_string())?;
    let pigz_fifo = pigz_case.join("trace.fifo");
    if !Command::new("mkfifo").arg(&pigz_fifo).status().map_err(|e| e.to_string())?.success() { return err("self-test pigz mkfifo failed"); }
    let pigz_out = pigz_case.join("trace.tsv.gz");
    let pigz_input = pigz_case.join("sample.tsv");
    let sample = b"time v(acsrc) v(acn)\n0.0 1.0 0.0\n0.1 2.0 0.0\n";
    fs::write(&pigz_input, sample).map_err(|e| e.to_string())?;
    let pigz_cmd = compressor_shell_command(pigz, &pigz_fifo, &pigz_out);
    let mut pigz_reader = Command::new("sh").arg("-c").arg(pigz_cmd).spawn().map_err(|e| e.to_string())?;
    let pigz_producer_cmd = format!("cat {} > {}", shell_quote(&pigz_input), shell_quote(&pigz_fifo));
    let mut pigz_producer = Command::new("sh").arg("-c").arg(pigz_producer_cmd).spawn().map_err(|e| e.to_string())?;
    if !pigz_producer.wait().map_err(|e| e.to_string())?.success() { return err("self-test pigz producer failed"); }
    if !wait_bounded(&mut pigz_reader, Duration::from_secs(2))?.success() || !pigz_out.is_file() { return err("self-test pigz reader did not finish"); }
    let pigz_gunzip = Command::new("gzip").args(["-cd", pigz_out.to_str().ok_or("pigz output path")?]).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?;
    let pigz_decoded = pigz_gunzip.wait_with_output().map_err(|e| e.to_string())?;
    if !pigz_decoded.status.success() || pigz_decoded.stdout != sample { return err("self-test pigz gzip-compatible roundtrip failed"); }
    let _ = fs::remove_file(&pigz_fifo);
    // A compressor/redirection failure is a failure and must not be promoted.
    let bad_fifo = delayed.join("bad.fifo");
    if !Command::new("mkfifo").arg(&bad_fifo).status().map_err(|e| e.to_string())?.success() { return err("self-test bad mkfifo failed"); }
    let bad_out = delayed.join("directory-output"); fs::create_dir_all(&bad_out).map_err(|e| e.to_string())?;
    let mut bad = Command::new("sh").arg("-c").arg(format!("exec gzip -c < '{}' > '{}'", bad_fifo.display(), bad_out.display())).spawn().map_err(|e| e.to_string())?;
    let mut bad_producer = Command::new("sh").arg("-c").arg(format!("printf payload > '{}'", bad_fifo.display())).spawn().map_err(|e| e.to_string())?;
    let _ = bad_producer.wait();
    let bad_status = wait_bounded(&mut bad, Duration::from_secs(2))?;
    if bad_status.success() { return err("self-test compressor failure was accepted"); }
    let _ = fs::remove_file(&bad_fifo);
    // Producer exits before opening the FIFO: explicitly reap the reader.
    let orphan_fifo = delayed.join("orphan.fifo");
    if !Command::new("mkfifo").arg(&orphan_fifo).status().map_err(|e| e.to_string())?.success() { return err("self-test orphan mkfifo failed"); }
    let mut orphan = Command::new("sh").arg("-c").arg(format!("exec gzip -c < '{}' > '{}'", orphan_fifo.display(), delayed.join("orphan.gz").display())).spawn().map_err(|e| e.to_string())?;
    let host = Command::new("sh").args(["-c", "exit 19"]).status().map_err(|e| e.to_string())?;
    if host.success() { return err("self-test producer failure unexpectedly passed"); }
    let _ = orphan.kill(); let _ = orphan.wait(); let _ = fs::remove_file(&orphan_fifo);
    if Command::new("/path/that/does/not/exist").spawn().is_ok() { return err("self-test missing executable unexpectedly spawned"); }
    Ok(())
}

fn is_fifo(path: &Path) -> Result<bool, String> {
    let ty = fs::symlink_metadata(path).map_err(|e| e.to_string())?.file_type();
    #[cfg(unix)] { Ok(ty.is_fifo()) }
    #[cfg(not(unix))] { let _ = ty; Ok(false) }
}

#[cfg(unix)]
fn write_exec(path: &Path, body: &str) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    fs::write(path, body).map_err(|e| e.to_string())?;
    let mut p = fs::metadata(path).map_err(|e| e.to_string())?.permissions();
    p.set_mode(0o755); fs::set_permissions(path, p).map_err(|e| e.to_string())
}

#[cfg(not(unix))]
fn write_exec(_: &Path, _: &str) -> Result<(), String> { err("self-test requires a Unix host") }

#[cfg(test)]
mod parent_tests {
    use super::*;

    #[test]
    fn timed_out_pipeline_reaps_every_child() {
        let mut first = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let mut second = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let result = wait_pipeline_children(&mut [&mut first, &mut second], Duration::from_millis(100), Path::new("/private/tmp"));
        assert!(result.unwrap_err().contains("exceeded"));
        assert!(first.try_wait().unwrap().is_some());
        assert!(second.try_wait().unwrap().is_some());
    }

    #[test]
    fn unreadable_disk_capacity_reaps_every_child() {
        let mut child = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let result = wait_pipeline_children(&mut [&mut child], Duration::from_secs(5), Path::new("/no-such-matrix07-disk-path"));
        assert!(result.unwrap_err().contains("free space"));
        assert!(child.try_wait().unwrap().is_some());
    }

    #[test]
    fn real_native_metadata_contract_is_readable() {
        validate_native_metadata(Path::new("host/normal-native-host-12/parent-smoke")).unwrap();
    }
}
