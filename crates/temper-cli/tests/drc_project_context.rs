//! Focused subprocess tests for `temper drc`'s KiCad project preflight.
#![cfg(unix)]

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

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
            "#!/bin/sh\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--output\" ]; then cp '{}' \"$arg\"; fi\n  previous=\"$arg\"\ndone\n",
            report_path.display()
        ),
    );

    Command::new(binary())
        .args(["drc", "--pcb", "sample.kicad_pcb"])
        .current_dir(&root)
        .env("PATH", prepend_path(&bin_dir))
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("spawn temper drc")
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

/// The same 0.2 mm track passes the default width check and fails only when
/// the CLI installs the generated 0.5 mm custom rule beside the renamed board.
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

    let rules = "(version 1)\n(rule \"custom-width-witness\"\n  (condition \"A.Type == 'Track'\")\n  (constraint track_width (min 0.5mm)))\n";
    fs::create_dir_all(root.join("pcb")).expect("create generator output directory");
    fs::create_dir_all(root.join(".venv/bin")).expect("create generator stub directory");
    // Replace only the rule generator. The CLI and KiCad execute normally.
    executable(
        &root.join(".venv/bin/python"),
        &format!("#!/bin/sh\ncat > pcb/temper.kicad_dru <<'RULES'\n{rules}RULES\n"),
    );
    let out = Command::new(binary())
        .args(["drc", "--pcb", "renamed.kicad_pcb"])
        .current_dir(&board_dir)
        .env("TEMPER_REPO_ROOT", &root)
        .output()
        .expect("run CLI with native KiCad");
    assert!(
        out.status.success(),
        "CLI failed: stdout={} stderr={}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        String::from_utf8_lossy(&out.stdout).contains("[error] track_width: 1"),
        "custom width rule was not enforced: {}",
        String::from_utf8_lossy(&out.stdout)
    );
    assert_eq!(
        fs::read_to_string(pcb).expect("read board after DRC"),
        board
    );
    assert_eq!(
        fs::read_to_string(board_dir.join("renamed.kicad_dru")).expect("read installed rules"),
        rules
    );
}
