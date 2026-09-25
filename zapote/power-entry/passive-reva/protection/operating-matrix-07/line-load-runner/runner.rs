//! Bounded, fail-closed line/load orchestration for matrix-07.
//!
//! This binary is intentionally an orchestrator.  It does not calculate an
//! engineering limit or reinterpret the operating-point checker.  It binds
//! each generated deck to an accepted cold-source receipt, runs at most four
//! independent tracked ngspice hosts, and forwards every raw trace through
//! the maintained normalizer and checker.

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

const MAX_WORKERS: usize = 4;
const DEFAULT_WORKERS: usize = 2;
const DEFAULT_WALL_LIMIT: u64 = 1800;
const DEFAULT_END_S: f64 = 0.5;

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
    spice_scripts: Option<PathBuf>,
    pigz: Option<PathBuf>,
    workers: usize,
    wall_limit: u64,
    end_s: f64,
    first_invalid_snapshot: bool,
    selected_cases: Option<Vec<String>>,
    self_test: bool,
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
        let _ = fs::remove_file(self.dir.join("trace.fifo"));
    }
}

fn usage() -> &'static str {
    "usage: line-load-runner --source DIR --baseline RECEIPT.json --manifest manifest.json \
     --output DIR --tracked /path/matrix07-tracked --normalize /path/matrix07-normalize \
     --checker /path/matrix07-checker [--spice-scripts DIR] [--workers 2..4] \
     [--wall-limit SEC] [--end-s SECONDS] [--pigz PATH] [--cases LL01,LL02]\n\
     or: line-load-runner --self-test"
}

fn err<T>(msg: impl Into<String>) -> Result<T, String> { Err(msg.into()) }

fn parse_args() -> Result<Config, String> {
    let mut args = env::args().skip(1).peekable();
    let mut c = Config {
        source_dir: PathBuf::new(), baseline: PathBuf::new(), manifest: PathBuf::new(),
        output: PathBuf::new(), tracked: PathBuf::new(), normalize: PathBuf::new(),
        checker: PathBuf::new(), spice_scripts: None, pigz: None, workers: DEFAULT_WORKERS,
        wall_limit: DEFAULT_WALL_LIMIT, end_s: DEFAULT_END_S, first_invalid_snapshot: false,
        selected_cases: None, self_test: false,
    };
    while let Some(arg) = args.next() {
        let value = |name: &str, args: &mut std::iter::Peekable<Skip<std::env::Args>>| {
            args.next().ok_or_else(|| format!("{name} requires a value"))
        };
        match arg.as_str() {
            "--self-test" => c.self_test = true,
            "--source" => c.source_dir = PathBuf::from(value("--source", &mut args)?),
            "--baseline" => c.baseline = PathBuf::from(value("--baseline", &mut args)?),
            "--manifest" => c.manifest = PathBuf::from(value("--manifest", &mut args)?),
            "--output" => c.output = PathBuf::from(value("--output", &mut args)?),
            "--tracked" => c.tracked = PathBuf::from(value("--tracked", &mut args)?),
            "--normalize" => c.normalize = PathBuf::from(value("--normalize", &mut args)?),
            "--checker" => c.checker = PathBuf::from(value("--checker", &mut args)?),
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
    if c.workers == 0 || c.workers > MAX_WORKERS { return err("--workers must be between 1 and 4"); }
    if c.pigz.is_some() && c.workers != DEFAULT_WORKERS { return err("--pigz currently requires --workers 2"); }
    if c.wall_limit == 0 || !c.end_s.is_finite() || c.end_s <= 0.0 { return err("positive wall limit and end time required"); }
    for (name, p) in [("--source", &c.source_dir), ("--baseline", &c.baseline),
                      ("--manifest", &c.manifest), ("--output", &c.output),
                      ("--tracked", &c.tracked), ("--normalize", &c.normalize),
                      ("--checker", &c.checker)] {
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

fn sha256_file(path: &Path) -> Result<String, String> { hash_bytes(&fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?) }

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

fn tracked_args(wall_limit: u64, end_s: f64, first_invalid_snapshot: bool) -> Vec<String> {
    let mut args = vec!["cold.cir".to_string(), wall_limit.to_string(), end_s.to_string(), "trace.fifo".to_string()];
    if first_invalid_snapshot { args.push("first-invalid.tsv".to_string()); }
    args
}

fn run_pipeline(case: &Path, normalize: &Path, checker: &Path, rload: f64, end_s: f64) -> Result<ExitStatus, String> {
    let gz = case.join("trace.tsv.gz");
    let mut gunzip = Command::new("gzip").args(["-cd", gz.to_str().ok_or("invalid gzip path")?]).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?;
    let gunzip_stdout = gunzip.stdout.take().ok_or_else(|| { reap_child(&mut gunzip); "gzip stdout".to_string() })?;
    let mut adapter = match Command::new(normalize).arg(format!("{rload:.12}")).stdin(gunzip_stdout).stdout(Stdio::piped()).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut gunzip); return err(format!("normalize spawn: {e}")); }
    };
    let report = match File::create(case.join("checker-report.txt")) {
        Ok(f) => f,
        Err(e) => { reap_child(&mut adapter); reap_child(&mut gunzip); return err(format!("checker report: {e}")); }
    };
    let adapter_stdout = adapter.stdout.take().ok_or_else(|| { reap_child(&mut adapter); reap_child(&mut gunzip); "adapter stdout".to_string() })?;
    let mut check = match Command::new(checker).args(["--end-s", &format!("{end_s:.12}")]).stdin(adapter_stdout).stdout(Stdio::from(report)).stderr(Stdio::inherit()).spawn() {
        Ok(c) => c,
        Err(e) => { reap_child(&mut adapter); reap_child(&mut gunzip); return err(format!("checker spawn: {e}")); }
    };
    let check_status = check.wait().map_err(|e| e.to_string())?;
    let adapter_status = adapter.wait().map_err(|e| e.to_string())?;
    let gzip_status = gunzip.wait().map_err(|e| e.to_string())?;
    if !gzip_status.success() || !adapter_status.success() { return err(format!("pipeline failed gzip={gzip_status} normalize={adapter_status}")); }
    Ok(check_status)
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
    if let Some(s) = c.spice_scripts.take() { c.spice_scripts = Some(fs::canonicalize(s).map_err(|e| format!("spice scripts: {e}"))?); }
    let compressor = compressor_for(c.pigz.as_deref())?;
    let baseline = read_text(&c.baseline)?;
    // jq performs strict JSON parsing and all semantic validation. The raw
    // key-count guard rejects duplicate critical keys, which JSON parsers
    // commonly collapse with last-key-wins semantics.
    for key in ["status", "accepted", "endpoint_s", "target_end_s", "deck_sha256", "includes_sha256"] {
        if json_key_count(&baseline, key) > 1 { return err(format!("baseline contains duplicate {key} key")); }
    }
    let valid = jq(&c.baseline, r#"if (type=="object" and .status=="accepted" and .accepted==true and ((.endpoint_s // .target_end_s)|type=="number") and ((.endpoint_s // .target_end_s)|isfinite) and ((.endpoint_s // .target_end_s)>0) and (.deck_sha256|type=="string" and test("^[0-9a-f]{64}$")) and (.includes_sha256|type=="string" and test("^[0-9a-f]{64}$"))) then "ok" else error("baseline is not an accepted hash-bound receipt") end"#)?;
    if valid.trim() != "ok" { return err("baseline receipt is not explicitly accepted; refusing to execute grid"); }
    let baseline_end = jq(&c.baseline, r#"(.endpoint_s // .target_end_s)"#)?.trim().parse::<f64>().map_err(|_| "baseline endpoint is invalid")?;
    if !baseline_end.is_finite() || baseline_end <= 0.0 || (baseline_end - c.end_s).abs() > 1e-12 {
        return err(format!("requested --end-s {} does not match accepted baseline endpoint {}", c.end_s, baseline_end));
    }
    let deck = c.source_dir.join("cold.cir");
    let deck_hash = sha256_file(&deck)?;
    let names = include_names(&c.source_dir)?;
    let inc_hash = include_digest(&c.source_dir, &names)?;
    let baseline_deck = jq(&c.baseline, ".deck_sha256")?;
    let baseline_inc = jq(&c.baseline, ".includes_sha256")?;
    if baseline_deck.trim() != deck_hash || baseline_inc.trim() != inc_hash {
        return err("baseline receipt hashes do not match current source deck/include closure");
    }
    // Parse and validate all nine manifest rows before applying an optional
    // selection. A staged run must never use selection as a way to bypass
    // malformed or duplicate rows in the original manifest.
    let all_points = parse_points(&c.manifest)?;
    let points = select_points(all_points, c.selected_cases.as_deref())?;
    let selected_ids: Vec<String> = points.iter().map(|point| point.id.clone()).collect();
    if c.output.exists() { return err(format!("output already exists: {} (refusing overwrite)", c.output.display())); }
    fs::create_dir_all(&c.output).map_err(|e| e.to_string())?;
    fs::write(c.output.join("source-identity.json"), format!("{{\n  \"deck_sha256\": \"{deck_hash}\",\n  \"includes_sha256\": \"{inc_hash}\",\n  \"tracked_sha256\": \"{}\",\n  \"normalize_sha256\": \"{}\",\n  \"checker_sha256\": \"{}\",\n  \"baseline\": \"{}\",\n  \"selected_cases\": {},\n  \"selection_mode\": \"{}\",\n  \"tracked_cli_args\": {:?},\n  \"first_invalid_snapshot\": {},\n  \"compressor\": {{\"path\": \"{}\", \"sha256\": \"{}\", \"threads\": {}, \"format\": \"{}\"}}\n}}\n", sha256_file(&c.tracked)?, sha256_file(&c.normalize)?, sha256_file(&c.checker)?, c.baseline.display(), json_string_array(&selected_ids), if c.selected_cases.is_some() { "explicit" } else { "default_all" }, tracked_args(c.wall_limit, c.end_s, c.first_invalid_snapshot), c.first_invalid_snapshot, compressor.path.display(), sha256_file(&compressor.path)?, compressor.threads, if compressor.pigz { "gzip-compatible-pigz" } else { "gzip" })).map_err(|e| e.to_string())?;
    let mut queue: VecDeque<_> = points.into_iter().collect();
    let mut active: Vec<Running> = Vec::new();
    let mut failures = 0;
    let mut progress = File::create(c.output.join("runner-progress.tsv")).map_err(|e| e.to_string())?;
    writeln!(progress, "runner_wall_s\tcase\ttracked_wall_s\tsim_s\tpercent\tsim_per_wall\tcallbacks").map_err(|e| e.to_string())?;
    while !queue.is_empty() || !active.is_empty() {
        while active.len() < c.workers {
            let Some(point) = queue.pop_front() else { break; };
            let dir = c.output.join(&point.id);
            let _ = materialize_deck(&c.source_dir, &dir, &point)?;
            let fifo = dir.join("trace.fifo");
            let fifo_status = Command::new("mkfifo").arg(&fifo).status().map_err(|e| e.to_string())?;
            if !fifo_status.success() || !is_fifo(&fifo)? { return err(format!("mkfifo failed for {}", point.id)); }
            let compressor_cmd = compressor_shell_command(&compressor, &fifo, &dir.join("trace.tsv.gz"));
            let gzip = Command::new("sh").arg("-c").arg(compressor_cmd).stdout(Stdio::null()).stderr(File::create(dir.join("gzip.log")).map_err(|e| e.to_string())?).spawn().map_err(|e| e.to_string())?;
            let log = match File::create(dir.join("run.log")) {
                Ok(f) => f,
                Err(e) => { let mut g = gzip; let _ = g.kill(); let _ = g.wait(); let _ = fs::remove_file(&fifo); return err(format!("run.log: {e}")); }
            };
            let tracked_arg_strings = tracked_args(c.wall_limit, c.end_s, c.first_invalid_snapshot);
            let tracked_args_ref: Vec<&str> = tracked_arg_strings.iter().map(String::as_str).collect();
            let mut cmd = Command::new(&c.tracked);
            let log_copy = match log.try_clone() {
                Ok(f) => f,
                Err(e) => { let mut g = gzip; let _ = g.kill(); let _ = g.wait(); let _ = fs::remove_file(&fifo); return err(format!("run.log clone: {e}")); }
            };
            cmd.current_dir(&dir).args(&tracked_args_ref).stdout(log_copy).stderr(Stdio::from(log));
            if let Some(s) = &c.spice_scripts { cmd.env("SPICE_SCRIPTS", s); }
            let child = match cmd.spawn() {
                Ok(c) => c,
                Err(e) => { let mut g = gzip; let _ = g.kill(); let _ = g.wait(); let _ = fs::remove_file(&fifo); return err(format!("spawn {}: {e}", point.id)); }
            };
            eprintln!("started {} (workers {}/{})", point.id, active.len() + 1, c.workers);
            active.push(Running { point, dir, child, compressor: gzip, started: Instant::now(), last_progress: String::new() });
        }
        let mut i = 0;
        while i < active.len() {
            let r = &mut active[i];
            if let Ok(Some(status)) = r.child.try_wait() {
                // The tracked producer has closed the FIFO by the time it
                // exits. Wait for compression to finish before opening the
                // gzip, otherwise the checker can observe a truncated file.
                let gzip_result = if status.success() {
                    wait_bounded(&mut r.compressor, Duration::from_secs(120))
                } else {
                    let _ = r.compressor.kill(); let _ = r.compressor.wait();
                    Err("tracked host failed before complete FIFO export".to_string())
                };
                let pipeline = if status.success() && gzip_result.as_ref().map(|s| s.success()).unwrap_or(false) && r.dir.join("trace.tsv.gz").is_file() {
                    run_pipeline(&r.dir, &c.normalize, &c.checker, r.point.rload, c.end_s)
                } else { Err(format!("tracked/compressor incomplete: tracked={status}, compressor={gzip_result:?}")) };
                let result = match pipeline {
                    Ok(s) if s.success() => { eprintln!("{} ACCEPTED by checker", r.point.id); "accepted" },
                    Ok(s) => { eprintln!("{} REJECTED by checker ({s})", r.point.id); failures += 1; "rejected" },
                    Err(e) => { eprintln!("{} runner failure: {e}", r.point.id); failures += 1; "runner_failure" },
                };
                fs::write(r.dir.join("result.json"), format!("{{\n  \"id\": \"{}\",\n  \"status\": \"{result}\",\n  \"tracked_exit\": {},\n  \"elapsed_s\": {:.3}\n}}\n", r.point.id, status.code().unwrap_or(-1), r.started.elapsed().as_secs_f64())).map_err(|e| e.to_string())?;
                let _ = fs::remove_file(r.dir.join("trace.fifo"));
                active.swap_remove(i);
                continue;
            }
            if r.started.elapsed() > Duration::from_secs(c.wall_limit.saturating_add(600)) {
                let _ = r.child.kill(); let _ = r.child.wait(); let _ = r.compressor.kill(); let _ = r.compressor.wait(); failures += 1;
                fs::write(r.dir.join("result.json"), format!("{{\n  \"id\": \"{}\",\n  \"status\": \"scheduler_timeout\"\n}}\n", r.point.id)).map_err(|e| e.to_string())?;
                let _ = fs::remove_file(r.dir.join("trace.fifo"));
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
    let final_status = if c.selected_cases.is_some() { "selected_cases_checker_accepted" } else { "all_checker_accepted" };
    fs::write(c.output.join("status.json"), format!("{{\"status\":\"{final_status}\",\"selected_cases\":{}}}\n", json_string_array(&selected_ids))).map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    match parse_args().and_then(|c| if c.self_test { self_test() } else { main_run(c) }) {
        Ok(()) => {}, Err(e) => { eprintln!("ERROR: {e}"); std::process::exit(1); }
    }
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
    let four = tracked_args(1800, 0.5, false);
    let five = tracked_args(1800, 0.5, true);
    if four != ["cold.cir", "1800", "0.5", "trace.fifo"] || five.len() != 5 || five[4] != "first-invalid.tsv" { return err("self-test tracked CLI protocol mismatch"); }
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
    println!("self-test: selection/materialization/hash/change-constraint/pipeline/process-fail-closed checks PASS");
    fs::remove_dir_all(&tmp).map_err(|e| e.to_string())?;
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
