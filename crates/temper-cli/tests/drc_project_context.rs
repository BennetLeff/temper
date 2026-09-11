//! Focused subprocess tests for `temper drc`'s KiCad project preflight.
#![cfg(unix)]

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};
use sha2::Digest;

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_temper"))
}

fn fixture_root(name: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock is after the Unix epoch")
        .as_nanos();
    let root =
        std::env::temp_dir().join(format!("temper-cli-{name}-{}-{nonce}", std::process::id()));
    fs::create_dir_all(root.join("scripts")).expect("create fixture scripts directory");
    fs::write(root.join("scripts/route_board.py"), "").expect("create repo marker");
    root
}

fn executable(path: &Path, contents: &str) {
    fs::write(path, contents).expect("write executable fixture");
    let mut permissions = fs::metadata(path)
        .expect("stat executable fixture")
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).expect("make fixture executable");
}

fn prepend_path(directory: &Path) -> String {
    let existing = std::env::var_os("PATH").unwrap_or_default();
    let mut paths = std::env::split_paths(&existing).collect::<Vec<_>>();
    paths.insert(0, directory.to_path_buf());
    std::env::join_paths(paths)
        .expect("fixture path entries are valid")
        .to_string_lossy()
        .into_owned()
}

fn drc_with_report(name: &str, report: &str) -> std::process::Output {
    drc_with_report_mode(name, report, false)
}

fn drc_with_report_mode(name: &str, report: &str, check: bool) -> std::process::Output {
    drc_with_fault(name, report, check, Fault::None)
}

#[derive(Clone, Copy)]
enum Fault {
    None,
    GeneratorFailure,
    KicadFailure,
    MissingReport,
    StaleReport,
}

fn drc_with_fault(name: &str, report: &str, check: bool, fault: Fault) -> std::process::Output {
    let root = fixture_root(name);
    let pcb = root.join("sample.kicad_pcb");
    fs::write(&pcb, "(kicad_pcb (version 20240108))").expect("create board fixture");
    fs::write(root.join("sample.kicad_pro"), "{}").expect("create project fixture");
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    let report_path = root.join("report.json");
    fs::write(&report_path, report).expect("write report fixture");
    let bin_dir = root.join("bin");
    let venv_bin = root.join(".venv/bin");
    fs::create_dir_all(&bin_dir).expect("create executable directory");
    fs::create_dir_all(&venv_bin).expect("create python fixture directory");
    let generator = if matches!(fault, Fault::GeneratorFailure) {
        "#!/bin/sh\nexit 1\n".to_string()
    } else if matches!(fault, Fault::StaleReport) {
        format!("#!/bin/sh\nset -eu\nmkdir -p \"$TMPDIR/temper-drc-$PPID\"\nprintf '{{\"violations\":[],\"unconnected_items\":[],\"included_severities\":[\"error\"],\"schematic_parity\":[]}}' > \"$TMPDIR/temper-drc-$PPID/drc.json\"\necho stale-seeded >&2\nprintf 'generated rules\\n' > '{}/temper.kicad_dru'\n", root.join("pcb").display())
    } else {
        format!("#!/bin/sh\nprintf 'generated rules\\n' > '{}/temper.kicad_dru'\n", root.join("pcb").display())
    };
    executable(&venv_bin.join("python"), &generator);
    let kicad = if matches!(fault, Fault::KicadFailure) {
        "#!/bin/sh\nexit 1\n".to_string()
    } else if matches!(fault, Fault::MissingReport | Fault::StaleReport) {
        "#!/bin/sh\nexit 0\n".to_string()
    } else {
        format!("#!/bin/sh\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--output\" ]; then cp '{}' \"$arg\"; fi\n  previous=\"$arg\"\ndone\n", report_path.display())
    };
    executable(&bin_dir.join("kicad-cli"), &kicad);

    let mut command = Command::new(binary());
    command.args(["drc", "--pcb", "sample.kicad_pcb"]);
    if check {
        command.arg("--check");
    }
    command
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TMPDIR", root.join("tmp"))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc")
}

#[derive(Clone, Copy)]
enum ReceiptMutation {
    None,
    Board,
    Project,
    Rules,
    Table,
    RemoveTable,
    MissingReport,
    KicadFailure,
    ClaimedOutput,
}

fn receipt_fixture(
    name: &str,
    report: &str,
    mutation: ReceiptMutation,
    existing_receipt: Option<&str>,
) -> (PathBuf, std::process::Output) {
    let root = fixture_root(name);
    let pcb = root.join("sample.kicad_pcb");
    let project = root.join("sample.kicad_pro");
    let table = root.join("fp-lib-table");
    fs::write(&pcb, "(kicad_pcb (version 20240108))").expect("create board fixture");
    fs::write(&project, "{}\n").expect("create project fixture");
    fs::write(&table, "(fp_lib_table (version 7))\n").expect("create table fixture");
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    let report_path = root.join("report.json");
    fs::write(&report_path, report).expect("write report fixture");
    let bin_dir = root.join("bin");
    fs::create_dir_all(&bin_dir).expect("create executable directory");
    fs::create_dir_all(root.join(".venv/bin")).expect("create python fixture directory");
    executable(
        &root.join(".venv/bin/python"),
        &format!("#!/bin/sh\nprintf 'generated rules\\n' > '{}/temper.kicad_dru'\n", root.join("pcb").display()),
    );
    let mutation_script = match mutation {
        ReceiptMutation::None => String::new(),
        ReceiptMutation::Board => format!("printf 'changed board\\n' > '{}'\n", pcb.display()),
        ReceiptMutation::Project => format!("printf 'changed project\\n' > '{}'\n", project.display()),
        ReceiptMutation::Rules => format!("printf 'changed rules\\n' > '{}/sample.kicad_dru'\n", root.display()),
        ReceiptMutation::Table => format!("printf 'changed table\\n' > '{}'\n", table.display()),
        ReceiptMutation::RemoveTable => format!("rm '{}'\n", table.display()),
        ReceiptMutation::MissingReport => "rm \"$report_output\"\n".to_string(),
        ReceiptMutation::KicadFailure => "exit 1\n".to_string(),
        ReceiptMutation::ClaimedOutput => "printf 'other writer\\n' > result.json\n".to_string(),
    };
    executable(
        &bin_dir.join("kicad-cli"),
        &format!(
            "#!/bin/sh\nset -eu\nprintf '%s\\n' \"$@\" > kicad-args.txt\nprevious=''\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--output\" ]; then cp '{}' \"$arg\"; report_output=\"$arg\"; fi\n  previous=\"$arg\"\ndone\n{}",
            report_path.display(), mutation_script
        ),
    );
    let receipt = root.join("result.json");
    if let Some(contents) = existing_receipt {
        fs::write(&receipt, contents).expect("write existing receipt");
    }
    let out = Command::new(binary())
        .args(["drc", "--check", "--pcb", "sample.kicad_pcb", "--receipt", "result.json"])
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TMPDIR", root.join("tmp"))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc");
    (root, out)
}

#[test]
fn drc_check_has_three_outcomes_and_requires_native_envelope() {
    for (name, report, expected) in [
        (
            "check-clean",
            r#"{"violations":[],"unconnected_items":[],"included_severities":["error","warning"],"schematic_parity":[]}"#,
            0,
        ),
        (
            "check-warning",
            r#"{"violations":[{"type":"clearance","severity":"warning"}],"unconnected_items":[],"included_severities":["error","warning"],"schematic_parity":[]}"#,
            0,
        ),
        (
            "check-error",
            r#"{"violations":[],"unconnected_items":[{"type":"unconnected_items","severity":"error"}],"included_severities":["error","warning"],"schematic_parity":[]}"#,
            1,
        ),
        (
            "check-incomplete",
            r#"{"violations":[],"unconnected_items":[]}"#,
            2,
        ),
        ("check-invalid-json", "{", 2),
        (
            "check-malformed-array",
            r#"{"violations":[],"unconnected_items":{},"included_severities":["error"]}"#,
            2,
        ),
        (
            "check-missing-type",
            r#"{"violations":[{"severity":"warning"}],"unconnected_items":[],"included_severities":["error"]}"#,
            2,
        ),
        (
            "check-errors-only-no-parity",
            r#"{"violations":[],"unconnected_items":[],"included_severities":["error"]}"#,
            0,
        ),
        (
            "check-missing-connectivity",
            r#"{"violations":[],"included_severities":["error"],"schematic_parity":[]}"#,
            2,
        ),
        (
            "check-missing-error-severity",
            r#"{"violations":[],"unconnected_items":[],"included_severities":["warning"],"schematic_parity":[]}"#,
            2,
        ),
        (
            "check-unknown-array",
            r#"{"violations":[],"unconnected_items":[],"included_severities":["error"],"new_findings":[],"schematic_parity":[]}"#,
            2,
        ),
        (
            "check-unknown-severity",
            r#"{"violations":[{"type":"clearance","severity":"notice"}],"unconnected_items":[],"included_severities":["error","warning"],"schematic_parity":[]}"#,
            2,
        ),
        (
            "check-parity-error",
            r#"{"violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[{"type":"parity","severity":"error"}]}"#,
            1,
        ),
        (
            "check-malformed-item",
            r#"{"violations":[null],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#,
            2,
        ),
        (
            "check-parity-warning",
            r#"{"violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[{"type":"parity","severity":"warning"}]}"#,
            0,
        ),
    ] {
        let out = drc_with_report_mode(name, report, true);
        assert_eq!(
            out.status.code(),
            Some(expected),
            "{name}: {}",
            String::from_utf8_lossy(&out.stderr)
        );
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert_eq!(
            stdout.lines().any(|line| line == "DRC check: no reported errors"),
            expected == 0,
            "{name}: {stdout}"
        );
        if expected == 2 {
            assert!(!stdout.contains("DRC violations:"), "{name}: {stdout}");
        }
    }
    for (name, fault) in [
        ("check-kicad-failure", Fault::KicadFailure),
        ("check-missing-report", Fault::MissingReport),
        ("check-generator-failure", Fault::GeneratorFailure),
        ("check-stale-report", Fault::StaleReport),
    ] {
        let out = drc_with_fault(name, r#"{}"#, true, fault);
        assert_eq!(out.status.code(), Some(2), "{name}: {}", String::from_utf8_lossy(&out.stderr));
        assert!(!String::from_utf8_lossy(&out.stdout).contains("no reported errors"));
        if matches!(fault, Fault::StaleReport) {
            assert!(String::from_utf8_lossy(&out.stderr).contains("stale-seeded"));
        }
    }
}

#[test]
fn drc_check_reports_errors_in_captured_native_report() {
    let report = include_str!(
        "../../../packages/temper-placer/tests/validation/fixtures/kicad_drc_reports/temper_26981fea_run0.json"
    );
    let out = drc_with_report_mode("check-captured-native", report, true);
    assert_eq!(out.status.code(), Some(1), "{}", String::from_utf8_lossy(&out.stderr));
    let stdout = String::from_utf8_lossy(&out.stdout);
    for expected in [
        "DRC violations: 1115",
        "  [error] unconnected_items: 339",
        "DRC check: reported errors (718)",
    ] {
        assert!(stdout.lines().any(|line| line == expected), "{stdout}");
    }
}

#[test]
fn drc_check_receipt_binds_raw_report_and_inputs() {
    let root = fixture_root("receipt");
    let pcb = root.join("sample.kicad_pcb");
    let project = root.join("sample.kicad_pro");
    fs::write(&pcb, "(kicad_pcb (version 20240108))").expect("create board fixture");
    fs::write(&project, "{}\n").expect("create project fixture");
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    let report = root.join("report.json");
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#;
    fs::write(&report, raw).expect("write report fixture");
    let bin_dir = root.join("bin");
    fs::create_dir_all(&bin_dir).expect("create executable directory");
    fs::create_dir_all(root.join(".venv/bin")).expect("create python fixture directory");
    executable(&root.join(".venv/bin/python"), &format!("#!/bin/sh\nprintf 'generated rules\\n' > '{}/temper.kicad_dru'\n", root.join("pcb").display()));
    executable(&bin_dir.join("kicad-cli"), &format!("#!/bin/sh\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--output\" ]; then cp '{}' \"$arg\"; fi\n  previous=\"$arg\"\ndone\n", report.display()));
    let receipt = root.join("result.json");
    let out = Command::new(binary())
        .args(["drc", "--check", "--pcb", "sample.kicad_pcb", "--receipt", "result.json"])
        .current_dir(&root).env("PATH", prepend_path(&bin_dir)).env("TMPDIR", root.join("tmp"))
        .env("TEMPER_REPO_ROOT", &root).output().expect("spawn temper drc");
    assert_eq!(out.status.code(), Some(0), "{}", String::from_utf8_lossy(&out.stderr));
    let receipt_json: serde_json::Value = serde_json::from_slice(&fs::read(&receipt).expect("read receipt")).expect("parse receipt");
    assert_eq!(receipt_json["schema_version"], 1);
    assert_eq!(receipt_json["report"]["raw"], raw);
    assert_eq!(receipt_json["report"]["sha256"], format!("{:x}", sha2::Sha256::digest(raw.as_bytes())));
    assert_eq!(receipt_json["kicad"]["version"], "10.0.5");
    assert_eq!(receipt_json["summary"]["verdict"], "pass");
    assert_eq!(receipt_json["inputs"]["fp_lib_table"]["present"], false);
    assert_eq!(receipt_json["inputs"]["generated_rules"]["sha256"], format!("{:x}", sha2::Sha256::digest(b"generated rules\n")));
}

#[test]
fn drc_check_receipt_binds_command_and_all_input_hashes() {
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#;
    let (root, out) = receipt_fixture("receipt-hashes", raw, ReceiptMutation::None, None);
    assert_eq!(out.status.code(), Some(0), "{}", String::from_utf8_lossy(&out.stderr));
    let value: serde_json::Value = serde_json::from_slice(&fs::read(root.join("result.json")).expect("read receipt")).expect("parse receipt");
    let args = value["kicad"]["command"].as_array().expect("command array");
    let invocation = fs::read_to_string(root.join("kicad-args.txt")).expect("read actual invocation");
    let expected: Vec<serde_json::Value> = std::iter::once("kicad-cli")
        .chain(invocation.lines()).map(serde_json::Value::from).collect();
    assert_eq!(args, &expected);
    assert_eq!(args.last().expect("board argument"), &fs::canonicalize(root.join("sample.kicad_pcb")).expect("resolve board").display().to_string());
    assert_eq!(value["inputs"]["board"]["sha256"], format!("{:x}", sha2::Sha256::digest(b"(kicad_pcb (version 20240108))")));
    assert_eq!(value["inputs"]["project"]["sha256"], format!("{:x}", sha2::Sha256::digest(b"{}\n")));
    assert_eq!(value["inputs"]["fp_lib_table"]["present"], true);
    assert_eq!(value["inputs"]["fp_lib_table"]["sha256"], format!("{:x}", sha2::Sha256::digest(b"(fp_lib_table (version 7))\n")));
}

#[test]
fn drc_check_receipt_publishes_failed_verdict_for_connectivity_error() {
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[{"type":"unconnected_items","severity":"error"}],"included_severities":["error"],"schematic_parity":[]}"#;
    let (root, out) = receipt_fixture("receipt-fail", raw, ReceiptMutation::None, None);
    assert_eq!(out.status.code(), Some(1), "{}", String::from_utf8_lossy(&out.stderr));
    let value: serde_json::Value = serde_json::from_slice(&fs::read(root.join("result.json")).expect("read receipt")).expect("parse receipt");
    assert_eq!(value["summary"]["verdict"], "fail");
    assert_eq!(value["summary"]["errors"], 1);
    assert_eq!(value["summary"]["counts"]["unconnected_items:error"], 1);
    assert_eq!(value["report"]["raw"], raw);
}

#[test]
fn drc_check_receipt_rejects_changed_inputs_without_receipt() {
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#;
    for (name, mutation) in [("board", ReceiptMutation::Board), ("project", ReceiptMutation::Project), ("rules", ReceiptMutation::Rules), ("table", ReceiptMutation::Table), ("remove-table", ReceiptMutation::RemoveTable)] {
        let (root, out) = receipt_fixture(&format!("receipt-mutated-{name}"), raw, mutation, None);
        assert_eq!(out.status.code(), Some(2), "{name}: {}", String::from_utf8_lossy(&out.stderr));
        assert!(!root.join("result.json").exists(), "{name}: changed input must not publish receipt");
        assert!(!String::from_utf8_lossy(&out.stdout).contains("DRC check:"), "{name}: receipt failure must not print verdict");
    }
}

#[test]
fn drc_check_receipt_rejects_bad_report_or_version_without_receipt() {
    for (name, raw) in [
        ("malformed", "{"),
        ("missing-version", r#"{"violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#),
        ("invalid-version", r#"{"kicad_version":4,"violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#),
        ("empty-version", r#"{"kicad_version":" ","violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#),
        ("incomplete", r#"{"kicad_version":"10.0.5","violations":[],"included_severities":["error"]}"#),
    ] {
        let (root, out) = receipt_fixture(&format!("receipt-{name}"), raw, ReceiptMutation::None, None);
        assert_eq!(out.status.code(), Some(2), "{name}: {}", String::from_utf8_lossy(&out.stderr));
        assert!(!root.join("result.json").exists(), "{name}: invalid report must not publish receipt");
        assert!(!String::from_utf8_lossy(&out.stdout).contains("DRC check:"), "{name}: incomplete receipt must not print verdict");
    }
}

#[test]
fn drc_receipt_does_not_publish_after_runner_failure_or_output_collision() {
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[],"included_severities":["error"]}"#;
    for (name, fault) in [("missing-output", ReceiptMutation::MissingReport), ("runner-failure", ReceiptMutation::KicadFailure), ("claimed-output", ReceiptMutation::ClaimedOutput)] {
        let (root, out) = receipt_fixture(name, raw, fault, None);
        assert_eq!(out.status.code(), Some(2), "{}", String::from_utf8_lossy(&out.stderr));
        assert!(!String::from_utf8_lossy(&out.stdout).contains("DRC check:"));
        if matches!(fault, ReceiptMutation::ClaimedOutput) {
            assert_eq!(fs::read_to_string(root.join("result.json")).expect("other writer's output"), "other writer\n");
        } else {
            assert!(!root.join("result.json").exists());
        }
    }
}

#[test]
fn drc_check_receipt_preserves_existing_output_and_refuses_missing_table_alias() {
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[],"included_severities":["error"],"schematic_parity":[]}"#;
    let (root, out) = receipt_fixture("receipt-existing", raw, ReceiptMutation::None, Some("sentinel\n"));
    assert_eq!(out.status.code(), Some(2));
    assert_eq!(fs::read_to_string(root.join("result.json")).expect("read existing receipt"), "sentinel\n");

    let root = fixture_root("receipt-missing-table-alias");
    fs::write(root.join("sample.kicad_pcb"), "(kicad_pcb (version 20240108))").expect("board");
    fs::write(root.join("sample.kicad_pro"), "{}\n").expect("project");
    fs::create_dir_all(root.join("pcb")).expect("generator dir");
    fs::create_dir_all(root.join(".venv/bin")).expect("python dir");
    executable(&root.join(".venv/bin/python"), &format!("#!/bin/sh\nprintf 'rules\\n' > '{}/temper.kicad_dru'\n", root.join("pcb").display()));
    let bin = root.join("bin"); fs::create_dir_all(&bin).expect("bin dir"); executable(&bin.join("kicad-cli"), "#!/bin/sh\nexit 1\n");
    let out = Command::new(binary()).args(["drc", "--check", "--pcb", "sample.kicad_pcb", "--receipt", "fp-lib-table"]).current_dir(&root).env("PATH", prepend_path(&bin)).env("TEMPER_REPO_ROOT", &root).output().expect("spawn");
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("must not alias a DRC input"), "{}", String::from_utf8_lossy(&out.stderr));
    assert!(!root.join("fp-lib-table").exists(), "missing table alias must not be created");
}

#[test]
fn drc_receipt_requires_check() {
    let out = Command::new(binary()).args(["drc", "--pcb", "missing.kicad_pcb", "--receipt", "result.json"]).output().expect("spawn temper");
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("--check"));
}

#[test]
#[cfg(target_os = "linux")] // APFS rejects these names before the CLI can read them.
fn drc_receipt_rejects_non_utf8_input_paths_without_panicking() {
    use std::os::unix::ffi::OsStringExt;
    let raw = r#"{"kicad_version":"10.0.5","violations":[],"unconnected_items":[],"included_severities":["error"]}"#;
    let (root, setup) = receipt_fixture("receipt-non-utf8", raw, ReceiptMutation::None, None);
    assert!(setup.status.success());
    let pcb = root.join(std::ffi::OsString::from_vec(b"board-\xff.kicad_pcb".to_vec()));
    fs::write(&pcb, "(kicad_pcb)").expect("non-UTF8 board");
    fs::write(pcb.with_extension("kicad_pro"), "{}").expect("project");
    let receipt = root.join("unicode-check.json");
    let out = Command::new(binary()).args(["drc", "--check", "--pcb"]).arg(&pcb)
        .arg("--receipt").arg(&receipt).current_dir(&root)
        .env("PATH", prepend_path(&root.join("bin"))).env("TEMPER_REPO_ROOT", &root)
        .output().expect("spawn non-UTF8 check");
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("valid UTF-8"));
    assert!(!receipt.exists());
}

#[test]
fn drc_rejects_board_without_matching_project_before_kicad() {
    let root = fixture_root("missing-project");
    let pcb = root.join("sample.kicad_pcb");
    fs::write(&pcb, "(kicad_pcb (version 20240108))").expect("create board fixture");
    let marker = root.join("kicad-invoked");
    let generation_marker = root.join("generation-invoked");
    let bin_dir = root.join("bin");
    let venv_bin = root.join(".venv/bin");
    fs::create_dir_all(&bin_dir).expect("create executable directory");
    fs::create_dir_all(&venv_bin).expect("create python fixture directory");
    executable(
        &venv_bin.join("python"),
        &format!("#!/bin/sh\ntouch '{}'\n", generation_marker.display()),
    );
    executable(
        &bin_dir.join("kicad-cli"),
        &format!("#!/bin/sh\ntouch '{}'\n", marker.display()),
    );

    let out = Command::new(binary())
        .args(["drc", "--pcb"])
        // A relative input must be resolved before the subprocess changes
        // cwd to TEMPER_REPO_ROOT.
        .arg("sample.kicad_pcb")
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc");

    assert!(!out.status.success(), "missing project must fail");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains(&root.join("sample.kicad_pro").display().to_string()));
    assert!(!marker.exists(), "kicad-cli must not run on rejected input");
    assert!(
        !generation_marker.exists(),
        "DRU generation must not run on rejected input"
    );

    let out = Command::new(binary())
        .args(["drc", "--check", "--pcb"])
        .arg("sample.kicad_pcb")
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn checked temper drc");
    assert_eq!(out.status.code(), Some(2), "checked preflight must be indeterminate");

    fs::create_dir(root.join("sample.kicad_pro")).expect("create project directory fixture");
    let out = Command::new(binary())
        .args(["drc", "--pcb"])
        .arg("sample.kicad_pcb")
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc for directory project");
    assert!(
        !out.status.success(),
        "project directory must fail preflight"
    );
    assert!(
        !marker.exists(),
        "kicad-cli must not run for a project directory"
    );
    assert!(
        !generation_marker.exists(),
        "DRU generation must not run for a project directory"
    );
}

#[test]
fn drc_accepts_matching_project_context_before_running_kicad() {
    let root = fixture_root("with-project");
    let board_dir = root.join("fixture");
    fs::create_dir_all(&board_dir).expect("create board fixture directory");
    let pcb = board_dir.join("sample.kicad_pcb");
    fs::write(&pcb, "(kicad_pcb (version 20240108))").expect("create board fixture");
    fs::write(board_dir.join("sample.kicad_pro"), "{}").expect("create project fixture");
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    let marker = root.join("kicad-invoked");
    let bin_dir = root.join("bin");
    let venv_bin = root.join(".venv/bin");
    fs::create_dir_all(&bin_dir).expect("create executable directory");
    fs::create_dir_all(&venv_bin).expect("create python fixture directory");
    executable(
        &venv_bin.join("python"),
        &format!(
            "#!/bin/sh\nprintf 'generated rules\\n' > '{}'/temper.kicad_dru\n",
            root.join("pcb").display()
        ),
    );
    executable(
        &bin_dir.join("kicad-cli"),
        &format!(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > '{}'\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--output\" ]; then printf '{{\"violations\":[]}}' > \"$arg\"; fi\n  previous=\"$arg\"\ndone\n",
            marker.display()
        ),
    );

    let out = Command::new(binary())
        .args(["drc", "--pcb"])
        .arg("sample.kicad_pcb")
        .current_dir(&board_dir)
        .env("PATH", prepend_path(&bin_dir))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc");

    assert!(
        out.status.success(),
        "valid project context must proceed: stderr={}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        marker.exists(),
        "kicad-cli should run after preflight succeeds"
    );
    let kicad_args = fs::read_to_string(&marker).expect("read recorded kicad arguments");
    let resolved_pcb = fs::canonicalize(&pcb).expect("resolve fixture board path");
    assert!(
        kicad_args
            .lines()
            .any(|arg| arg == resolved_pcb.to_string_lossy()),
        "kicad-cli must receive the requested board's absolute path, got:\n{kicad_args}"
    );
    assert_eq!(
        fs::read_to_string(board_dir.join("sample.kicad_dru")).expect("installed rule sidecar"),
        "generated rules\n",
        "rules must be installed beside the requested board stem"
    );
}

#[test]
fn drc_refuses_to_replace_unrelated_board_rules() {
    let root = fixture_root("conflicting-rules");
    let pcb = root.join("sample.kicad_pcb");
    fs::write(&pcb, "(kicad_pcb (version 20240108))").expect("create board fixture");
    fs::write(root.join("sample.kicad_pro"), "{}").expect("create project fixture");
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    fs::write(root.join("sample.kicad_dru"), "caller rules\n").expect("create caller rules");
    let bin_dir = root.join("bin");
    let venv_bin = root.join(".venv/bin");
    fs::create_dir_all(&bin_dir).expect("create executable directory");
    fs::create_dir_all(&venv_bin).expect("create python fixture directory");
    executable(
        &venv_bin.join("python"),
        &format!(
            "#!/bin/sh\nprintf 'generated rules\\n' > '{}'/temper.kicad_dru\n",
            root.join("pcb").display()
        ),
    );
    let marker = root.join("kicad-invoked");
    executable(
        &bin_dir.join("kicad-cli"),
        &format!("#!/bin/sh\ntouch '{}'\n", marker.display()),
    );

    let out = Command::new(binary())
        .args(["drc", "--pcb"])
        .arg(&pcb)
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc");

    assert!(!out.status.success(), "conflicting rules must fail closed");
    assert!(
        !marker.exists(),
        "kicad-cli must not run with conflicting rules"
    );
    assert_eq!(
        fs::read_to_string(root.join("sample.kicad_dru")).expect("caller rules remain"),
        "caller rules\n"
    );
}

#[test]
fn drc_summary_includes_connectivity_and_preserves_existing_findings() {
    let report = include_str!(
        "../../../packages/temper-placer/tests/validation/fixtures/kicad_drc_reports/temper_26981fea_run0.json"
    );
    let out = drc_with_report("connectivity-summary", report);
    assert!(
        out.status.success(),
        "DRC report should parse: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.lines().any(|line| line == "DRC violations: 1115"), "{stdout}");
    assert!(stdout.lines().any(|line| line == "  [error] unconnected_items: 339"), "{stdout}");
    assert!(stdout.lines().any(|line| line == "  [error] clearance: 179"), "{stdout}");
}

#[test]
fn drc_summary_reports_connectivity_only_findings() {
    let out = drc_with_report(
        "connectivity-only-summary",
        r#"{"violations":[],"unconnected_items":[{"type":"unconnected_items","severity":"error"}]}"#,
    );
    assert!(
        out.status.success(),
        "DRC report should parse: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.lines().any(|line| line == "DRC violations: 1"), "{stdout}");
    assert!(stdout.lines().any(|line| line == "  [error] unconnected_items: 1"), "{stdout}");
}

#[test]
fn drc_summary_accepts_missing_or_empty_connectivity_array() {
    for (name, report, expected_total, expected_line) in [
        (
            "connectivity-missing",
            r#"{"violations":[{"type":"clearance","severity":"warning"}]}"#,
            1,
            Some("  [warning] clearance: 1"),
        ),
        (
            "connectivity-empty",
            r#"{"violations":[],"unconnected_items":[]}"#,
            0,
            None,
        ),
    ] {
        let out = drc_with_report(name, report);
        assert!(
            out.status.success(),
            "{name}: {}",
            String::from_utf8_lossy(&out.stderr)
        );
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(
            stdout
                .lines()
                .any(|line| line == format!("DRC violations: {expected_total}")),
            "{stdout}"
        );
        if let Some(expected_line) = expected_line {
            assert!(stdout.lines().any(|line| line == expected_line), "{stdout}");
        }
    }
}

#[test]
fn drc_summary_rejects_malformed_connectivity_array() {
    for (name, report) in [
        (
            "connectivity-malformed-object",
            r#"{"violations":[],"unconnected_items":{}}"#,
        ),
        (
            "connectivity-malformed-null",
            r#"{"violations":[],"unconnected_items":null}"#,
        ),
        (
            "connectivity-malformed-entry",
            r#"{"violations":[],"unconnected_items":[null]}"#,
        ),
    ] {
        let out = drc_with_report(name, report);
        assert!(!out.status.success(), "{name} must fail");
        let stdout = String::from_utf8_lossy(&out.stdout);
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(stderr.contains("unconnected_items"));
        assert!(!stdout.contains("DRC violations:"));
    }
}

/// Native KiCad verifies all three check outcomes on the same 0.2 mm track:
/// permissive rules pass, a 0.5 mm minimum fails, and missing context exits 2.
#[test]
#[ignore = "requires native KiCad; run explicitly with --ignored --exact"]
fn drc_native_enforces_custom_rule_for_renamed_board() {
    let root = fixture_root("native-custom-rule");
    let board_dir = root.join("fixture");
    fs::create_dir_all(&board_dir).expect("create board directory");
    let pcb = board_dir.join("renamed.kicad_pcb");
    let board = r#"(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0))
  (net 0 "")
  (net 1 "WITNESS")
  (gr_rect (start 0 0) (end 30 20) (stroke (width 0.05) (type default))
    (fill none) (layer "Edge.Cuts") (tstamp 8a4f6ef4-5b28-4001-9111-000000000001))
  (segment (start 10 10) (end 20 10) (width 0.2) (layer "F.Cu") (net 1)
    (tstamp 8a4f6ef4-5b28-4001-9111-000000000002))
)
"#;
    fs::write(&pcb, board).expect("write one-track board");
    fs::write(board_dir.join("renamed.kicad_pro"), "{}\n").expect("write project");
    // No footprints: an empty local table is the complete library context.
    fs::write(
        board_dir.join("fp-lib-table"),
        "(fp_lib_table (version 7))\n",
    )
    .expect("write footprint table");

    let control_report = root.join("control.json");
    let control = Command::new("kicad-cli")
        .args([
            "pcb",
            "drc",
            "--all-track-errors",
            "--format",
            "json",
            "--output",
        ])
        .arg(&control_report)
        .arg(&pcb)
        .output()
        .expect("native KiCad must be available for this explicitly requested test");
    assert!(
        control.status.success(),
        "native control failed: {}",
        String::from_utf8_lossy(&control.stderr)
    );
    let control_json: serde_json::Value =
        serde_json::from_slice(&fs::read(control_report).expect("read control report"))
            .expect("parse control report");
    let violations = control_json["violations"]
        .as_array()
        .expect("violation array");
    assert!(
        violations.iter().all(|v| v["type"] != "track_width"),
        "the witness must not fail the default track-width rule: {violations:?}"
    );

    let permissive_rules = "(version 1)\n(rule \"custom-width-witness\"\n  (condition \"A.Type == 'Track'\")\n  (constraint track_width (min 0.1mm)))\n";
    let strict_rules = "(version 1)\n(rule \"custom-width-witness\"\n  (condition \"A.Type == 'Track'\")\n  (constraint track_width (min 0.5mm)))\n";
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    fs::create_dir_all(root.join(".venv/bin")).expect("create generator stub directory");
    // Replace only the rule generator. The CLI and KiCad execute normally.
    executable(
        &root.join(".venv/bin/python"),
        &format!("#!/bin/sh\ncat > pcb/temper.kicad_dru <<'RULES'\n{permissive_rules}RULES\n"),
    );
    let permissive_receipt = root.join("permissive-receipt.json");
    let out = Command::new(binary())
        .args(["drc", "--check", "--pcb", "renamed.kicad_pcb", "--receipt"])
        .arg(&permissive_receipt)
        .current_dir(&board_dir)
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("run CLI with native KiCad");
    assert!(
        out.status.success(),
        "permissive native check failed: stdout={} stderr={}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(String::from_utf8_lossy(&out.stdout)
        .lines().any(|line| line == "DRC check: no reported errors"));
    assert_eq!(
        fs::read_to_string(board_dir.join("renamed.kicad_dru")).expect("read permissive installed rules"),
        permissive_rules
    );
    assert!(permissive_receipt.is_file(), "passing native check should publish receipt");
    let permissive_json: serde_json::Value = serde_json::from_slice(&fs::read(&permissive_receipt).expect("read passing receipt")).expect("parse passing receipt");
    assert_eq!(permissive_json["summary"]["verdict"], "pass");
    assert_eq!(permissive_json["summary"]["errors"], 0);
    assert_eq!(permissive_json["inputs"]["generated_rules"]["sha256"], format!("{:x}", sha2::Sha256::digest(permissive_rules.as_bytes())));
    fs::remove_file(board_dir.join("renamed.kicad_dru")).expect("remove installed permissive rules");
    executable(
        &root.join(".venv/bin/python"),
        &format!("#!/bin/sh\ncat > pcb/temper.kicad_dru <<'RULES'\n{strict_rules}RULES\n"),
    );
    let strict_receipt = root.join("strict-receipt.json");
    let out = Command::new(binary())
        .args(["drc", "--check", "--pcb", "renamed.kicad_pcb", "--receipt"])
        .arg(&strict_receipt)
        .current_dir(&board_dir)
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("run strict CLI with native KiCad");
    assert_eq!(out.status.code(), Some(1), "strict native check: stdout={} stderr={}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    let stdout = String::from_utf8_lossy(&out.stdout);
    for expected in ["  [error] track_width: 1", "DRC check: reported errors (1)"] {
        assert!(stdout.lines().any(|line| line == expected), "{stdout}");
    }
    assert_eq!(
        fs::read_to_string(board_dir.join("renamed.kicad_dru")).expect("read strict installed rules"),
        strict_rules
    );
    assert!(strict_receipt.is_file(), "failing native check should publish receipt");
    let strict_json: serde_json::Value = serde_json::from_slice(&fs::read(&strict_receipt).expect("read strict receipt")).expect("parse strict receipt");
    assert_eq!(strict_json["summary"]["verdict"], "fail");
    assert_eq!(strict_json["summary"]["errors"], 1);
    assert_eq!(strict_json["summary"]["counts"]["track_width:error"], 1);
    assert_eq!(strict_json["inputs"]["board"]["sha256"], permissive_json["inputs"]["board"]["sha256"]);
    assert_eq!(strict_json["inputs"]["generated_rules"]["sha256"], format!("{:x}", sha2::Sha256::digest(strict_rules.as_bytes())));
    let native_raw = strict_json["report"]["raw"].as_str().expect("native raw report");
    let native_report: serde_json::Value = serde_json::from_str(native_raw).expect("native report JSON");
    assert_eq!(strict_json["kicad"]["version"], native_report["kicad_version"]);
    assert_eq!(strict_json["report"]["sha256"], format!("{:x}", sha2::Sha256::digest(native_raw.as_bytes())));
    fs::remove_file(board_dir.join("renamed.kicad_pro")).expect("remove project context");
    let out = Command::new(binary())
        .args(["drc", "--check", "--pcb", "renamed.kicad_pcb"])
        .current_dir(&board_dir)
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("run missing-context CLI");
    assert_eq!(out.status.code(), Some(2), "missing project must be indeterminate: {}", String::from_utf8_lossy(&out.stderr));
    assert!(String::from_utf8_lossy(&out.stderr).contains("missing KiCad project context"));
    assert!(!String::from_utf8_lossy(&out.stdout).contains("DRC check:"));
    assert_eq!(fs::read_to_string(pcb).expect("read board after DRC"), board);
    assert_eq!(
        fs::read_to_string(board_dir.join("renamed.kicad_dru")).expect("read installed rules"),
        strict_rules
    );
}
