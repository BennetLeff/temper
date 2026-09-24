//! Source-locked preintegration inventory. Compile with `rustc --edition=2021`.
//! `verify --replay` executes recorded tools without a shell; use only trusted receipts.
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

const ROLES: &[(&str, &str)] = &[
    ("power_entry_source", "source"),
    ("auxiliary_source", "source"),
    ("discharge_source", "source"),
    ("inverter_source", "source"),
    ("cooling_source", "source"),
    ("programming_ui_source", "source"),
    ("sensing_and_gate_sources", "source"),
    ("integrated_source", "source"),
    ("integrated_pcb", "board"),
    ("firmware", "source"),
    ("adopted_rust_suite", "machine"),
    ("native_erc", "machine"),
    ("native_drc", "machine"),
    ("exact_bom", "machine"),
    ("fab_outputs", "machine"),
    ("assembly_outputs", "machine"),
    ("isolation", "physical"),
    ("control_loss_default_off", "physical"),
    ("vd_stop_and_discharge", "physical"),
    ("vb_stop_and_discharge", "physical"),
    ("thermal", "physical"),
    ("assembled_campaign", "physical"),
];

#[derive(Clone, Debug)]
struct Entry {
    path: String,
    sha: String,
    receipt: String,
    receipt_sha: String,
}

#[derive(Debug)]
struct Manifest {
    stage: String,
    frozen_board_sha: String,
    entries: BTreeMap<String, Entry>,
}

#[derive(Debug)]
struct Receipt {
    role: String,
    artifact_sha: String,
    board_sha: String,
    tool: String,
    tool_sha: String,
    tool_version: String,
    args: Vec<String>,
    exit_code: i32,
    raw_path: String,
    raw_sha: String,
}

fn sha256(path: &Path) -> Result<String, String> {
    // shasum is a platform tool, not an acceptance oracle. It hashes exact bytes.
    let out = Command::new("shasum")
        .arg("-a")
        .arg("256")
        .arg(path)
        .output()
        .map_err(|e| format!("shasum invocation: {e}"))?;
    if !out.status.success() {
        return Err(format!("cannot hash {}", path.display()));
    }
    let s = String::from_utf8(out.stdout).map_err(|e| e.to_string())?;
    let hash = s.split_whitespace().next().ok_or("empty shasum output")?;
    if !valid_hash(hash) {
        return Err("malformed shasum output".into());
    }
    Ok(hash.into())
}

fn valid_hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

fn safe_path(root: &Path, p: &str) -> Result<PathBuf, String> {
    if p.is_empty()
        || p == "-"
        || Path::new(p).is_absolute()
        || p.split('/').any(|s| s == ".." || s.is_empty())
    {
        return Err(format!("invalid relative path: {p}"));
    }
    let root = root.canonicalize().map_err(|e| e.to_string())?;
    let path = root.join(p);
    let canonical = path
        .canonicalize()
        .map_err(|e| format!("{}: {e}", path.display()))?;
    if !canonical.starts_with(&root) || !canonical.is_file() {
        return Err(format!("path escapes root or is not a file: {p}"));
    }
    Ok(canonical)
}

fn new_output_path(root: &Path, p: &str) -> Result<PathBuf, String> {
    if p.is_empty()
        || p == "-"
        || Path::new(p).is_absolute()
        || p.split('/').any(|s| s == ".." || s.is_empty())
    {
        return Err(format!("invalid output path: {p}"));
    }
    let root = root.canonicalize().map_err(|e| e.to_string())?;
    let path = root.join(p);
    let parent = path.parent().ok_or("output has no parent")?;
    let parent = parent.canonicalize().map_err(|e| e.to_string())?;
    if !parent.starts_with(&root) || path.exists() {
        return Err("output escapes root or already exists".into());
    }
    Ok(path)
}

fn parse_manifest(s: &str) -> Result<Manifest, String> {
    let mut lines = s.lines();
    let stage = lines
        .next()
        .ok_or("missing stage")?
        .split_once('\t')
        .ok_or("malformed stage")?;
    if stage.0 != "stage" || !["preintegration", "frozen_integrated"].contains(&stage.1) {
        return Err("invalid stage".into());
    }
    let board = lines
        .next()
        .ok_or("missing frozen board hash")?
        .split_once('\t')
        .ok_or("malformed frozen board hash")?;
    if board.0 != "frozen_board_sha256" || board.1 != "-" && !valid_hash(board.1) {
        return Err("invalid frozen board hash".into());
    }
    if lines.next() != Some("role\tartifact\tsha256\treceipt\treceipt_sha256") {
        return Err("invalid manifest header".into());
    }
    let registry: BTreeSet<&str> = ROLES.iter().map(|(r, _)| *r).collect();
    let mut entries = BTreeMap::new();
    for line in lines {
        let cols: Vec<_> = line.split('\t').collect();
        if cols.len() != 5 || !registry.contains(cols[0]) {
            return Err(format!("unknown role or malformed row: {line}"));
        }
        if entries.contains_key(cols[0]) {
            return Err(format!("duplicate role: {}", cols[0]));
        }
        if (cols[1] == "-") != (cols[2] == "-") || cols[1] != "-" && !valid_hash(cols[2]) {
            return Err(format!("invalid artifact/hash pair: {}", cols[0]));
        }
        if cols[1] == "-" && cols[3] != "-" {
            return Err(format!("receipt without artifact: {}", cols[0]));
        }
        if (cols[3] == "-") != (cols[4] == "-") || cols[4] != "-" && !valid_hash(cols[4]) {
            return Err(format!("invalid receipt/hash pair: {}", cols[0]));
        }
        if cols[1] != "-"
            && (cols[1].is_empty() || cols[1].contains("..") || cols[1].starts_with('/'))
        {
            return Err(format!("invalid artifact path: {}", cols[0]));
        }
        entries.insert(
            cols[0].into(),
            Entry {
                path: cols[1].into(),
                sha: cols[2].into(),
                receipt: cols[3].into(),
                receipt_sha: cols[4].into(),
            },
        );
    }
    let missing: Vec<_> = registry
        .into_iter()
        .filter(|r| !entries.contains_key(*r))
        .collect();
    if !missing.is_empty() {
        return Err(format!("missing roles: {}", missing.join(",")));
    }
    if stage.1 == "preintegration" && board.1 != "-" {
        return Err("preintegration cannot pin a release board".into());
    }
    if stage.1 == "frozen_integrated" && board.1 == "-" {
        return Err("frozen stage lacks board hash".into());
    }
    Ok(Manifest {
        stage: stage.1.into(),
        frozen_board_sha: board.1.into(),
        entries,
    })
}

fn one<'a>(rows: &'a BTreeMap<String, Vec<String>>, key: &str) -> Result<&'a str, String> {
    let v = rows
        .get(key)
        .ok_or_else(|| format!("missing receipt field {key}"))?;
    if v.len() != 1 || v[0].is_empty() {
        return Err(format!("invalid receipt field {key}"));
    }
    Ok(&v[0])
}

fn parse_receipt(s: &str) -> Result<Receipt, String> {
    let allowed: BTreeSet<&str> = [
        "kind",
        "role",
        "artifact_sha256",
        "board_sha256",
        "tool",
        "tool_sha256",
        "tool_version",
        "arg",
        "exit_code",
        "raw_path",
        "raw_sha256",
    ]
    .into_iter()
    .collect();
    let mut rows: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for line in s.lines() {
        let (k, v) = line.split_once('\t').ok_or("malformed receipt line")?;
        if !allowed.contains(k) {
            return Err(format!("unknown receipt field {k}"));
        }
        rows.entry(k.into()).or_default().push(v.into());
    }
    if one(&rows, "kind")? != "release-check-v1" {
        return Err("wrong receipt kind".into());
    }
    let receipt = Receipt {
        role: one(&rows, "role")?.into(),
        artifact_sha: one(&rows, "artifact_sha256")?.into(),
        board_sha: one(&rows, "board_sha256")?.into(),
        tool: one(&rows, "tool")?.into(),
        tool_sha: one(&rows, "tool_sha256")?.into(),
        tool_version: one(&rows, "tool_version")?.into(),
        args: rows.get("arg").cloned().unwrap_or_default(),
        exit_code: one(&rows, "exit_code")?
            .parse()
            .map_err(|_| "invalid exit code")?,
        raw_path: one(&rows, "raw_path")?.into(),
        raw_sha: one(&rows, "raw_sha256")?.into(),
    };
    if ![
        &receipt.artifact_sha,
        &receipt.board_sha,
        &receipt.tool_sha,
        &receipt.raw_sha,
    ]
    .iter()
    .all(|s| valid_hash(s))
    {
        return Err("invalid receipt hash".into());
    }
    if receipt
        .args
        .iter()
        .any(|arg| arg.contains('\n') || arg.contains('\t'))
    {
        return Err("invalid argument".into());
    }
    Ok(receipt)
}

fn output_bytes(out: &std::process::Output) -> Vec<u8> {
    let mut bytes = out.stdout.clone();
    bytes.extend_from_slice(&out.stderr);
    bytes
}

fn tool_version(tool: &Path, role: &str) -> Result<String, String> {
    let version_arg = if role == "adopted_rust_suite" {
        "--version"
    } else {
        "version"
    };
    let out = Command::new(tool)
        .arg(version_arg)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err("tool version command failed".into());
    }
    let value = String::from_utf8(output_bytes(&out)).map_err(|e| e.to_string())?;
    let value = value.trim();
    if value.is_empty() || value.contains('\t') || value.contains('\n') {
        return Err("invalid tool version".into());
    }
    Ok(value.into())
}

fn expected_tool(role: &str) -> Option<&'static str> {
    match role {
        "adopted_rust_suite" => Some("cargo"),
        "native_erc" | "native_drc" | "exact_bom" | "fab_outputs" | "assembly_outputs" => {
            Some("kicad-cli")
        }
        _ => None,
    }
}

fn tool_path(root: &Path, text: &str) -> Result<PathBuf, String> {
    let path = if Path::new(text).is_absolute() {
        PathBuf::from(text)
    } else {
        safe_path(root, text)?
    };
    let path = path.canonicalize().map_err(|e| e.to_string())?;
    if !path.is_file() {
        return Err("tool is not a file".into());
    }
    Ok(path)
}

fn command_shape(role: &str, args: &[String], board: &Path, artifact: &Path) -> Result<(), String> {
    let prefix: &[&str] = match role {
        "native_erc" => &["sch", "erc"],
        "native_drc" => &["pcb", "drc"],
        "exact_bom" => &["sch", "export"],
        "fab_outputs" | "assembly_outputs" => &["pcb", "export"],
        "adopted_rust_suite" => &[],
        _ => return Err("non-machine role cannot carry a check receipt".into()),
    };
    if !args
        .iter()
        .map(String::as_str)
        .take(prefix.len())
        .eq(prefix.iter().copied())
    {
        return Err("wrong command family for role".into());
    }
    let required = match role {
        "adopted_rust_suite" => &["run", "test"][..],
        "exact_bom" => &["bom"][..],
        "fab_outputs" => &["gerbers", "drill"][..],
        "assembly_outputs" => &["pos"][..],
        _ => &[][..],
    };
    if !required.is_empty() && !args.iter().any(|a| required.contains(&a.as_str())) {
        return Err("missing role-specific command".into());
    }
    let board = board.to_str().ok_or("invalid board path")?;
    let artifact = artifact.to_str().ok_or("invalid artifact path")?;
    if !args.iter().any(|a| a == board) || !args.iter().any(|a| a == artifact) {
        return Err("command must name exact integrated board and output artifact".into());
    }
    Ok(())
}

fn replay(
    root: &Path,
    role: &str,
    artifact_path: &str,
    artifact_sha: &str,
    board_sha: &str,
    receipt_path: &str,
    receipt_sha: &str,
) -> Result<bool, String> {
    let path = safe_path(root, receipt_path)?;
    if sha256(&path)? != receipt_sha {
        return Err("receipt bytes changed".into());
    }
    let receipt = parse_receipt(&fs::read_to_string(path).map_err(|e| e.to_string())?)?;
    if receipt.role != role
        || receipt.artifact_sha != artifact_sha
        || receipt.board_sha != board_sha
    {
        return Err("receipt role/artifact/board identity mismatch".into());
    }
    let tool = tool_path(root, &receipt.tool)?;
    if tool.file_name().and_then(|s| s.to_str()) != expected_tool(role) {
        return Err("tool not allowed for role".into());
    }
    if sha256(&tool)? != receipt.tool_sha || tool_version(&tool, role)? != receipt.tool_version {
        return Err("tool bytes/version changed".into());
    }
    let raw = safe_path(root, &receipt.raw_path)?;
    if sha256(&raw)? != receipt.raw_sha {
        return Err("raw output changed".into());
    }
    let board = safe_path(root, "zapote/integration/cooker.kicad_pcb")?;
    let artifact = safe_path(root, artifact_path)?;
    command_shape(role, &receipt.args, &board, &artifact)?;
    let out = Command::new(&tool)
        .args(&receipt.args)
        .output()
        .map_err(|e| e.to_string())?;
    let code = out
        .status
        .code()
        .ok_or("tool terminated without exit code")?;
    if code != receipt.exit_code
        || output_bytes(&out) != fs::read(raw).map_err(|e| e.to_string())?
    {
        return Err("replay exit/output differs from receipt".into());
    }
    if sha256(&board)? != board_sha
        || sha256(&artifact)? != artifact_sha
        || sha256(&tool)? != receipt.tool_sha
    {
        return Err("replay changed board, artifact or tool bytes".into());
    }
    Ok(code == 0)
}

fn evaluate(
    root: &Path,
    m: &Manifest,
    replay_checks: bool,
) -> (Vec<(String, &'static str, String)>, bool) {
    let mut rows = Vec::new();
    let mut any_fail = false;
    let board_entry = &m.entries["integrated_pcb"];
    let board_ok = m.stage == "frozen_integrated"
        && board_entry.path == "zapote/integration/cooker.kicad_pcb"
        && board_entry.sha == m.frozen_board_sha
        && safe_path(root, &board_entry.path)
            .ok()
            .and_then(|p| sha256(&p).ok())
            .as_deref()
            == Some(&board_entry.sha);
    for &(role, kind) in ROLES {
        let e = &m.entries[role];
        let (status, reason) = if e.path == "-" {
            ("NOT_RUN", "absent evidence".to_string())
        } else {
            let artifact = safe_path(root, &e.path).and_then(|p| sha256(&p));
            let receipt_identity = if e.receipt == "-" {
                Ok(())
            } else {
                safe_path(root, &e.receipt)
                    .and_then(|p| sha256(&p))
                    .and_then(|actual| {
                        if actual == e.receipt_sha {
                            Ok(())
                        } else {
                            Err("receipt bytes changed".into())
                        }
                    })
            };
            match artifact {
                Err(err) => ("FAIL", err),
                Ok(hash) if hash != e.sha => ("FAIL", "artifact bytes changed".into()),
                Ok(_) if receipt_identity.is_err() => ("FAIL", receipt_identity.unwrap_err()),
                Ok(_) if kind == "source" => (
                    "INDETERMINATE",
                    "identity only; unit acceptance not replayed".into(),
                ),
                Ok(_) if kind == "board" && !board_ok => {
                    ("FAIL", "not the pinned integrated board".into())
                }
                Ok(_) if kind == "board" => (
                    "INDETERMINATE",
                    "board identity only; checks outstanding".into(),
                ),
                Ok(_) if kind == "physical" => (
                    "INDETERMINATE",
                    "requires independently reviewed article measurement".into(),
                ),
                Ok(_) if !board_ok => ("INDETERMINATE", "no pinned integrated board".into()),
                Ok(_) if e.receipt == "-" => ("NOT_RUN", "no machine receipt".into()),
                Ok(_) if !replay_checks => ("INDETERMINATE", "replay required".into()),
                Ok(_) => match replay(
                    root,
                    role,
                    &e.path,
                    &e.sha,
                    &board_entry.sha,
                    &e.receipt,
                    &e.receipt_sha,
                ) {
                    Ok(true) => ("PASS", "exact machine replay matched".into()),
                    Ok(false) => ("FAIL", "machine check exited nonzero".into()),
                    Err(err) => ("FAIL", err),
                },
            }
        };
        any_fail |= status == "FAIL";
        rows.push((role.into(), status, reason));
    }
    (rows, any_fail)
}

fn verify(root: &Path, manifest: &Path, replay_checks: bool) -> Result<bool, String> {
    let m = parse_manifest(&fs::read_to_string(manifest).map_err(|e| e.to_string())?)?;
    let (rows, fail) = evaluate(root, &m, replay_checks);
    println!("role\tstatus\treason");
    for (role, status, reason) in &rows {
        println!("{role}\t{status}\t{reason}");
    }
    let complete =
        m.stage == "frozen_integrated" && rows.iter().all(|(_, status, _)| *status == "PASS");
    println!(
        "RELEASE\t{}",
        if fail {
            "FAIL"
        } else if complete {
            "PASS"
        } else {
            "INCOMPLETE"
        }
    );
    Ok(!fail && complete)
}

fn capture(args: &[String]) -> Result<(), String> {
    // capture ROOT ROLE ARTIFACT BOARD TOOL RECEIPT RAW -- ARGS...
    if args.len() < 11 || args[9] != "--" {
        return Err("capture syntax".into());
    }
    let root = Path::new(&args[2]);
    let role = &args[3];
    let artifact = new_output_path(root, &args[4])?;
    let board = safe_path(root, &args[5])?;
    if args[5] != "zapote/integration/cooker.kicad_pcb" {
        return Err("not integrated board path".into());
    }
    let tool = tool_path(root, &args[6])?;
    if tool.file_name().and_then(|s| s.to_str()) != expected_tool(role) {
        return Err("tool not allowed for role".into());
    }
    let receipt_out = new_output_path(root, &args[7])?;
    let raw_out = new_output_path(root, &args[8])?;
    if receipt_out == raw_out {
        return Err("receipt/raw paths collide".into());
    }
    let command_args = &args[10..];
    if command_args
        .iter()
        .any(|s| s.contains('\n') || s.contains('\t'))
    {
        return Err("invalid command argument".into());
    }
    command_shape(role, command_args, &board, &artifact)?;
    let tool_version = tool_version(&tool, role)?;
    let tool_sha = sha256(&tool)?;
    let board_sha = sha256(&board)?;
    let output = Command::new(&tool)
        .args(command_args)
        .output()
        .map_err(|e| e.to_string())?;
    let exit = output
        .status
        .code()
        .ok_or("tool terminated without exit code")?;
    let artifact =
        safe_path(root, &args[4]).map_err(|_| "check did not produce the named output artifact")?;
    let artifact_sha = sha256(&artifact)?;
    fs::write(&raw_out, output_bytes(&output)).map_err(|e| e.to_string())?;
    let raw_sha = sha256(&raw_out)?;
    if sha256(&board)? != board_sha
        || sha256(&artifact)? != artifact_sha
        || sha256(&tool)? != tool_sha
    {
        return Err("capture changed board, artifact or tool bytes".into());
    }
    let mut receipt = format!("kind\trelease-check-v1\nrole\t{role}\nartifact_sha256\t{artifact_sha}\nboard_sha256\t{board_sha}\ntool\t{}\ntool_sha256\t{tool_sha}\ntool_version\t{tool_version}\n", tool.display());
    for arg in command_args {
        receipt.push_str(&format!("arg\t{arg}\n"));
    }
    receipt.push_str(&format!(
        "exit_code\t{exit}\nraw_path\t{}\nraw_sha256\t{raw_sha}\n",
        args[8]
    ));
    fs::write(&receipt_out, receipt).map_err(|e| e.to_string())?;
    println!("captured {role}: exit {exit}, board {board_sha}, raw {raw_sha}");
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("verify")
            if args.len() >= 4
                && args.len() <= 5
                && args.get(4).is_none_or(|s| s == "--replay") =>
        {
            match verify(Path::new(&args[2]), Path::new(&args[3]), args.len() == 5) {
                Ok(true) => ExitCode::SUCCESS,
                Ok(false) => ExitCode::from(1),
                Err(err) => {
                    eprintln!("FAIL: {err}");
                    ExitCode::from(2)
                }
            }
        }
        Some("capture") => match capture(&args) {
            Ok(()) => ExitCode::SUCCESS,
            Err(err) => {
                eprintln!("FAIL: {err}");
                ExitCode::from(2)
            }
        },
        _ => {
            eprintln!("usage: release_gate verify ROOT MANIFEST [--replay]\n       release_gate capture ROOT ROLE ARTIFACT BOARD TOOL RECEIPT RAW -- ARGS...");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    static NEXT: AtomicUsize = AtomicUsize::new(0);

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = env::temp_dir().join(format!(
                "zapote-release-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }
        fn put(&self, path: &str, bytes: &[u8]) -> String {
            let p = self.0.join(path);
            fs::create_dir_all(p.parent().unwrap()).unwrap();
            fs::write(&p, bytes).unwrap();
            sha256(&p).unwrap()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    fn manifest(rows: &[(&str, &str, &str, &str, &str)], stage: &str, board_hash: &str) -> String {
        let mut s = format!(
            "stage\t{stage}\nfrozen_board_sha256\t{board_hash}\nrole\tartifact\tsha256\treceipt\treceipt_sha256\n"
        );
        for (role, _) in ROLES {
            let (_, path, hash, receipt, receipt_hash) = rows
                .iter()
                .find(|r| r.0 == *role)
                .copied()
                .unwrap_or((role, "-", "-", "-", "-"));
            s.push_str(&format!(
                "{role}\t{path}\t{hash}\t{receipt}\t{receipt_hash}\n"
            ));
        }
        s
    }

    #[test]
    fn registry_rejects_missing_duplicate_and_unknown_roles() {
        let base = manifest(&[], "preintegration", "-");
        assert!(parse_manifest(&base).is_ok());
        assert!(parse_manifest(&base.replace("thermal\t-\t-\t-\t-\n", ""))
            .unwrap_err()
            .contains("missing roles"));
        assert!(parse_manifest(&(base.clone() + "thermal\t-\t-\t-\t-\n"))
            .unwrap_err()
            .contains("duplicate"));
        assert!(parse_manifest(&(base + "not_a_role\t-\t-\t-\t-\n"))
            .unwrap_err()
            .contains("unknown"));
    }

    #[test]
    fn handwritten_pass_is_not_a_manifest_field() {
        let bad = manifest(&[], "preintegration", "-")
            .replace("thermal\t-\t-\t-\t-", "thermal\t-\t-\tPASS\t-");
        // A receipt without an artifact is rejected, even if it says PASS.
        assert!(parse_manifest(&bad).is_err());
    }

    #[test]
    fn stale_source_bytes_fail() {
        let f = Fixture::new();
        let hash = f.put("source.ato", b"one");
        let m = parse_manifest(&manifest(
            &[("auxiliary_source", "source.ato", &hash, "-", "-")],
            "preintegration",
            "-",
        ))
        .unwrap();
        assert_eq!(evaluate(&f.0, &m, false).0[1].1, "INDETERMINATE");
        f.put("source.ato", b"two");
        assert_eq!(evaluate(&f.0, &m, false).0[1].1, "FAIL");
    }

    #[test]
    fn missing_source_receipt_fails_instead_of_becoming_accepted() {
        let f = Fixture::new();
        let hash = f.put("source.ato", b"source");
        let fake_receipt_hash = "0".repeat(64);
        let m = parse_manifest(&manifest(
            &[(
                "auxiliary_source",
                "source.ato",
                &hash,
                "absent.tsv",
                &fake_receipt_hash,
            )],
            "preintegration",
            "-",
        ))
        .unwrap();
        assert_eq!(evaluate(&f.0, &m, false).0[1].1, "FAIL");
    }

    #[test]
    fn standalone_board_substitution_fails_even_with_rehashed_bytes() {
        let f = Fixture::new();
        let hash = f.put("zapote/gate-drive/section.kicad_pcb", b"standalone");
        let m = parse_manifest(&manifest(
            &[(
                "integrated_pcb",
                "zapote/gate-drive/section.kicad_pcb",
                &hash,
                "-",
                "-",
            )],
            "frozen_integrated",
            &hash,
        ))
        .unwrap();
        assert_eq!(evaluate(&f.0, &m, false).0[8].1, "FAIL");
    }

    #[test]
    fn frozen_board_bytes_must_match_pin() {
        let f = Fixture::new();
        let hash = f.put("zapote/integration/cooker.kicad_pcb", b"board one");
        let m = parse_manifest(&manifest(
            &[(
                "integrated_pcb",
                "zapote/integration/cooker.kicad_pcb",
                &hash,
                "-",
                "-",
            )],
            "frozen_integrated",
            &hash,
        ))
        .unwrap();
        assert_eq!(evaluate(&f.0, &m, false).0[8].1, "INDETERMINATE");
        f.put("zapote/integration/cooker.kicad_pcb", b"board two");
        assert_eq!(evaluate(&f.0, &m, false).0[8].1, "FAIL");
    }

    #[cfg(unix)]
    fn fake_cargo(f: &Fixture, exit: i32) -> PathBuf {
        use std::os::unix::fs::PermissionsExt;
        let code = format!("#!/bin/sh\nif [ \"$1\" = '--version' ]; then printf 'cargo test 1\\n'; exit 0; fi\nprintf 'suite report' > \"$3\"\nprintf 'test output\\n'\nexit {exit}\n");
        f.put("cargo", code.as_bytes());
        let p = f.0.join("cargo");
        fs::set_permissions(&p, fs::Permissions::from_mode(0o755)).unwrap();
        p
    }

    #[cfg(unix)]
    fn captured(f: &Fixture, exit: i32) -> (String, String, String, String) {
        let board_sha = f.put("zapote/integration/cooker.kicad_pcb", b"integrated board");
        let cargo = fake_cargo(f, exit);
        let board =
            f.0.join("zapote/integration/cooker.kicad_pcb")
                .canonicalize()
                .unwrap();
        let artifact = f.0.canonicalize().unwrap().join("suite.log");
        let args = vec![
            "release_gate".into(),
            "capture".into(),
            f.0.to_str().unwrap().into(),
            "adopted_rust_suite".into(),
            "suite.log".into(),
            "zapote/integration/cooker.kicad_pcb".into(),
            cargo.to_str().unwrap().into(),
            "receipt.tsv".into(),
            "raw.log".into(),
            "--".into(),
            "run".into(),
            board.to_str().unwrap().into(),
            artifact.to_str().unwrap().into(),
        ];
        capture(&args).unwrap();
        let artifact_sha = sha256(&artifact).unwrap();
        (
            board_sha,
            artifact_sha,
            "receipt.tsv".into(),
            sha256(&f.0.join("receipt.tsv")).unwrap(),
        )
    }

    #[test]
    #[cfg(unix)]
    fn actual_replay_can_pass_a_machine_role_but_not_release() {
        let f = Fixture::new();
        let (board_sha, artifact_sha, receipt, receipt_sha) = captured(&f, 0);
        let m = parse_manifest(&manifest(
            &[
                (
                    "integrated_pcb",
                    "zapote/integration/cooker.kicad_pcb",
                    &board_sha,
                    "-",
                    "-",
                ),
                (
                    "adopted_rust_suite",
                    "suite.log",
                    &artifact_sha,
                    &receipt,
                    &receipt_sha,
                ),
            ],
            "frozen_integrated",
            &board_sha,
        ))
        .unwrap();
        assert_eq!(evaluate(&f.0, &m, false).0[10].1, "INDETERMINATE");
        assert_eq!(evaluate(&f.0, &m, true).0[10].1, "PASS");
        assert!(evaluate(&f.0, &m, true)
            .0
            .iter()
            .any(|(_, status, _)| *status != "PASS"));
    }

    #[test]
    #[cfg(unix)]
    fn replay_rejects_wrong_board_receipt_and_nonzero_exit() {
        let f = Fixture::new();
        let (board_sha, artifact_sha, receipt, receipt_sha) = captured(&f, 1);
        let m = parse_manifest(&manifest(
            &[
                (
                    "integrated_pcb",
                    "zapote/integration/cooker.kicad_pcb",
                    &board_sha,
                    "-",
                    "-",
                ),
                (
                    "adopted_rust_suite",
                    "suite.log",
                    &artifact_sha,
                    &receipt,
                    &receipt_sha,
                ),
            ],
            "frozen_integrated",
            &board_sha,
        ))
        .unwrap();
        assert_eq!(evaluate(&f.0, &m, true).0[10].1, "FAIL");
        let path = f.0.join("receipt.tsv");
        let text = fs::read_to_string(&path).unwrap().replace(
            &format!("board_sha256\t{board_sha}"),
            &format!("board_sha256\t{}", "0".repeat(64)),
        );
        fs::write(path, text).unwrap();
        assert_eq!(evaluate(&f.0, &m, true).0[10].1, "FAIL");
        let amended_receipt_sha = sha256(&f.0.join("receipt.tsv")).unwrap();
        let rehashed = parse_manifest(&manifest(
            &[
                (
                    "integrated_pcb",
                    "zapote/integration/cooker.kicad_pcb",
                    &board_sha,
                    "-",
                    "-",
                ),
                (
                    "adopted_rust_suite",
                    "suite.log",
                    &artifact_sha,
                    &receipt,
                    &amended_receipt_sha,
                ),
            ],
            "frozen_integrated",
            &board_sha,
        ))
        .unwrap();
        assert!(evaluate(&f.0, &rehashed, true).0[10]
            .2
            .contains("identity mismatch"));
    }

    #[test]
    #[cfg(unix)]
    fn replay_rejects_forged_raw_or_tool_bytes() {
        let f = Fixture::new();
        let (board_sha, artifact_sha, receipt, receipt_sha) = captured(&f, 0);
        let m = parse_manifest(&manifest(
            &[
                (
                    "integrated_pcb",
                    "zapote/integration/cooker.kicad_pcb",
                    &board_sha,
                    "-",
                    "-",
                ),
                (
                    "adopted_rust_suite",
                    "suite.log",
                    &artifact_sha,
                    &receipt,
                    &receipt_sha,
                ),
            ],
            "frozen_integrated",
            &board_sha,
        ))
        .unwrap();
        f.put("raw.log", b"forged PASS");
        assert_eq!(evaluate(&f.0, &m, true).0[10].1, "FAIL");
        f.put("raw.log", b"test output\n");
        f.put("cargo", b"#!/bin/sh\nexit 0\n");
        assert_eq!(evaluate(&f.0, &m, true).0[10].1, "FAIL");
    }
}
